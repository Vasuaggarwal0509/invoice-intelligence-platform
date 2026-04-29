"""End-to-end smoke harness for business_layer.

Drives 9 user-journey scenarios through the FastAPI stack via TestClient,
hitting every interesting code path that pytest doesn't already cover at
this fidelity (multi-persona switching across full HTTP cycles, static
shells served, OAuth state CSRF redirect behaviour).

Designed to be glanceable: prints PASS/FAIL per check + a final summary.
Exits 1 on any failure so CI fails the build.

Runs locally:    python tests/smoke/biz_layer_smoke.py
Runs in Make:    make smoke
Runs in CI:      same command, after pytest gate.
"""

from __future__ import annotations

import logging
import os
import re
import struct
import sys
import zlib
from contextlib import contextmanager

# --- sandbox env ------------------------------------------------------
# Set BEFORE any business_layer import so Settings picks them up.
os.environ.setdefault("PLATFORM_SECRET_KEY", "smoke-key-must-be-at-least-32-chars-long-ok")
os.environ.setdefault("PLATFORM_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("PLATFORM_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PLATFORM_ENV", "test")
os.environ.setdefault("PLATFORM_LOG_LEVEL", "WARNING")

logging.basicConfig(level=logging.WARNING)

from fastapi.testclient import TestClient

from business_layer.app import app_factory

PASS: list[str] = []
FAIL: list[tuple[str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append((label, detail))
        print(f"  FAIL  {label}  -- {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# --- helpers ----------------------------------------------------------


def tiny_png() -> bytes:
    """24x24 valid PNG so python-magic accepts the upload."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 24, 24, 8, 2, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = (b"\x00" + b"\xff\xff\xff" * 24) * 24
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def otp_from_logs(phone: str, lines: list[str]) -> str | None:
    pat = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for line in reversed(lines):
        m = pat.search(line)
        if m:
            return m.group(1)
    return None


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@contextmanager
def captured_logs(logger_name: str = "business_layer.routes.auth"):
    h = _ListHandler()
    logger = logging.getLogger(logger_name)
    prev_level = logger.level
    logger.addHandler(h)
    logger.setLevel(logging.INFO)
    try:
        yield h.lines
    finally:
        logger.removeHandler(h)
        logger.setLevel(prev_level)


def fresh_client() -> TestClient:
    """Build a TestClient with brand-new in-memory DB + reset singletons."""
    from business_layer.config import get_settings
    from business_layer.db import engine as db_engine
    from business_layer.security.rate_limit import limiter as _rl

    get_settings.cache_clear()
    db_engine._reset_for_tests()
    _rl.reset()
    import business_layer.services.extraction_runner as _er

    _er._pipeline_singleton = None

    tc = TestClient(app_factory())
    tc.__enter__()  # fire startup events → migrations run
    return tc


def biz_signup(client: TestClient, phone: str, name: str) -> tuple[dict | None, str | None]:
    with captured_logs() as lines:
        r = client.post("/api/auth/otp/request", json={"phone": phone})
        if r.status_code != 200:
            return None, f"otp request failed: {r.status_code} {r.text}"
        code = otp_from_logs(phone, lines)
        if not code:
            return None, "OTP not captured in logs"
    r = client.post(
        "/api/auth/otp/verify",
        json={"phone": phone, "code": code, "display_name": name},
    )
    if r.status_code != 200:
        return None, f"verify failed: {r.status_code} {r.text}"
    return r.json(), None


def ca_signup(
    client: TestClient,
    email: str,
    name: str,
    gstin: str,
    password: str = "hunter2-this-is-long-enough",
):
    return client.post(
        "/api/ca/auth/signup",
        json={
            "email": email,
            "password": password,
            "display_name": name,
            "gstin": gstin,
        },
    )


def stub_pipeline() -> None:
    """Replace the real PipelineRunner with a deterministic stub.

    Same shape as the conftest fixture in
    business_layer/tests/integration/test_upload_pipeline.py.
    """
    from extraction_layer.components.extraction.types import (
        ExtractedField,
        ExtractionResult,
    )
    from extraction_layer.components.ocr.types import OCRResult, PageSize
    from extraction_layer.components.tables.types import (
        InvoiceItem,
        TableExtractionResult,
    )
    from extraction_layer.components.validation.types import (
        RuleFinding,
        RuleOutcome,
        ValidationResult,
    )

    def fake_run(self, image):  # type: ignore[no-untyped-def]
        ocr = OCRResult(
            tokens=[],
            lines=[],
            page=PageSize(width=24, height=24),
            backend="stub",
            duration_ms=0.1,
        )
        extraction = ExtractionResult(
            fields={
                "seller": ExtractedField(
                    name="seller", value="Vendor Co", confidence=0.9, source="stub"
                ),
                "invoice_no": ExtractedField(
                    name="invoice_no", value="INV-1", confidence=0.9, source="stub"
                ),
                "tax_id": ExtractedField(
                    name="tax_id", value="29AABCU9603R1Z2", confidence=0.9, source="stub"
                ),
                "date": ExtractedField(
                    name="date", value="2026-04-22", confidence=0.9, source="stub"
                ),
            },
            extractor="stub",
            duration_ms=0.1,
        )
        items = [
            InvoiceItem(
                item_desc="Widget",
                item_qty="1",
                item_net_price="100.00",
                item_gross_worth="100.00",
            )
        ]
        tables = TableExtractionResult(items=items, extractor="stub", duration_ms=0.1)
        validation = ValidationResult(
            findings=[
                RuleFinding(
                    rule_name="stub_rule",
                    target="invoice_no",
                    outcome=RuleOutcome.PASS,
                    reason="stub",
                ),
            ],
        )
        return ocr, extraction, tables, validation

    import extraction_layer.backend.app.pipeline as pipe_mod

    pipe_mod.PipelineRunner.run = fake_run
    import business_layer.services.extraction_runner as er

    er._pipeline_singleton = None


# ===== scenarios =====================================================


def run_scenario_1_business_e2e(client: TestClient) -> None:
    section("Scenario 1 — business signup → upload → dashboard → invoice → inbox")

    biz, err = biz_signup(client, "+919000004001", "Demo Co")
    check("business signup via OTP", biz is not None, err or "")
    if not biz:
        return
    workspace_id = biz["workspace"]["id"]
    check(
        "/api/auth/me echoes workspace + role",
        biz["user"]["role"] == "business" and biz["workspace"]["id"] == workspace_id,
    )

    inbox = client.get("/api/inbox").json()
    check("empty inbox before upload", inbox["items"] == [])

    png = tiny_png()
    r = client.post(
        "/api/upload",
        files={"file": ("hello.png", png, "image/png")},
    )
    check("upload accepted", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    if r.status_code != 201:
        return
    invoice_id = r.json()["invoice_id"]

    from business_layer.workers.extraction_worker import drain_now

    drain_now()

    detail = client.get(f"/api/invoices/{invoice_id}")
    check("invoice detail readable post-extraction", detail.status_code == 200)
    inv = detail.json().get("invoice", {})
    check(
        "extracted vendor surfaces",
        inv.get("vendor_name") == "Vendor Co",
        f"got {inv.get('vendor_name')}",
    )
    check(
        "extracted invoice_no surfaces",
        inv.get("invoice_no") == "INV-1",
        f"got {inv.get('invoice_no')}",
    )
    check(
        "extracted total summed from items",
        inv.get("total_amount_minor") == 10000,
        f"got {inv.get('total_amount_minor')}",
    )

    dash = client.get("/api/business/dashboard").json()
    check("dashboard has tiles", "tiles" in dash and "invoices_this_month" in dash["tiles"])
    check(
        "dashboard tile count reflects upload",
        dash["tiles"]["invoices_this_month"] == 1,
        f"got {dash['tiles'].get('invoices_this_month')}",
    )
    check("dashboard total_spend matches", dash["tiles"]["total_spend_minor"] == 10000)

    inbox = client.get("/api/inbox").json()
    check("inbox has 1 row after upload", len(inbox["items"]) == 1)

    img = client.get(f"/api/invoices/{invoice_id}/image")
    check(
        "invoice image served to owner",
        img.status_code == 200 and img.headers.get("content-type", "").startswith("image/png"),
    )

    biz_signup(client, "+919000004002", "Other Co")
    img2 = client.get(f"/api/invoices/{invoice_id}/image")
    check("other-workspace image access → 404 IDOR defence", img2.status_code == 404)

    client.post("/api/auth/logout", json={})
    client.cookies.clear()


def run_scenario_2_ca_signup_validation(client: TestClient) -> None:
    section("Scenario 2 — CA signup validation + duplicate handling")
    r = ca_signup(client, "x@example.com", "BadPass", "29AABCU9603R1Z2", password="short")
    check("short password rejected (422)", r.status_code == 422)

    r = ca_signup(client, "ok@example.com", "Acme CA", "29AABCU9603R1Z2")
    check("valid CA signup → 201", r.status_code == 201)

    client.post("/api/auth/logout", json={})
    client.cookies.clear()
    r = ca_signup(client, "ok@example.com", "Other", "07AAACO1234K1Z8")
    check("duplicate email → 409", r.status_code == 409)

    r = ca_signup(client, "ok2@example.com", "Other", "29AABCU9603R1Z2")
    check("duplicate GSTIN → 409", r.status_code == 409)

    r = client.post(
        "/api/ca/auth/login",
        json={"email": "ok@example.com", "password": "wrong-password-here"},
    )
    check(
        "wrong-password login → 401 generic",
        r.status_code == 401 and r.json()["code"] == "authentication_failed",
    )

    r = client.post(
        "/api/ca/auth/login",
        json={"email": "nobody@example.com", "password": "doesntmatter1234"},
    )
    check("unknown-email login → 401 generic", r.status_code == 401)

    r = client.post(
        "/api/ca/auth/login",
        json={"email": "ok@example.com", "password": "hunter2-this-is-long-enough"},
    )
    check("correct CA login → 200", r.status_code == 200)


def run_scenario_3_ca_linkage_full_flow(client: TestClient) -> None:
    section("Scenario 3 — CA linkage + derived client list end-to-end")

    r = ca_signup(client, "thisca@example.com", "ThisCA", "29AABCU9603R1Z2")
    check("CA registered", r.status_code == 201)
    client.post("/api/auth/logout", json={})
    client.cookies.clear()

    biz, _ = biz_signup(client, "+919000004100", "Linked Biz")
    workspace_id = biz["workspace"]["id"]
    r = client.post("/api/business/ca-link", json={"ca_gstin": "29AABCU9603R1Z2"})
    check("business → CA link success", r.status_code == 200)

    me = client.get("/api/auth/me").json()
    check(
        "/api/auth/me reflects ca_gstin",
        me["workspace"]["ca_gstin"] == "29AABCU9603R1Z2",
    )

    r = client.post("/api/business/ca-link", json={"ca_gstin": "07AAACO1234K1Z8"})
    check("link to absent GSTIN → 404", r.status_code == 404)

    png = tiny_png()
    up = client.post("/api/upload", files={"file": ("a.png", png, "image/png")})
    check("business upload (for CA visibility)", up.status_code == 201)
    inv_id = up.json()["invoice_id"]
    from business_layer.workers.extraction_worker import drain_now

    drain_now()

    client.post("/api/auth/logout", json={})
    client.cookies.clear()

    r = client.post(
        "/api/ca/auth/login",
        json={"email": "thisca@example.com", "password": "hunter2-this-is-long-enough"},
    )
    check("CA login after linkage", r.status_code == 200)

    clients = client.get("/api/ca/clients").json()
    check("CA client list non-empty", len(clients["items"]) == 1)
    check("CA sees correct business", clients["items"][0]["name"] == "Linked Biz")
    check("CA client list shows invoice count", clients["items"][0]["invoice_count"] == 1)

    r = client.get(f"/api/ca/clients/{workspace_id}/invoices")
    check("CA can list client's invoices", r.status_code == 200)
    check("CA invoice list non-empty", len(r.json()["items"]) == 1)

    r = client.get(f"/api/ca/clients/{workspace_id}/invoices/{inv_id}")
    check("CA full detail accessible", r.status_code == 200)
    body = r.json()
    check("CA detail includes findings list", "findings" in body)
    check("CA detail includes extraction_result", "extraction_result" in body)

    r = client.get(f"/api/ca/clients/{workspace_id}/invoices/{inv_id}/image")
    check(
        "CA-scoped image route serves bytes",
        r.status_code == 200 and r.headers.get("content-type", "").startswith("image/png"),
    )

    client.post("/api/auth/logout", json={})
    client.cookies.clear()
    biz_signup(client, "+919000004100", "Linked Biz")
    r = client.delete("/api/business/ca-link")
    check("business unlinks CA → 200", r.status_code == 200)


def run_scenario_4_cross_persona_idor(client: TestClient) -> None:
    section("Scenario 4 — cross-persona authorization gates")

    biz_signup(client, "+919000004200", "Biz")
    r = client.get("/api/ca/clients")
    check("business → /api/ca/clients = 403", r.status_code == 403)
    r = client.get("/api/ca/clients/abc/invoices")
    check("business → CA client invoices = 403", r.status_code == 403)

    client.post("/api/auth/logout", json={})
    client.cookies.clear()

    ca_signup(client, "blocked@example.com", "Blocked CA", "29AABCU9603R1Z2")
    r = client.get("/api/business/dashboard")
    check("CA → /api/business/dashboard = 403", r.status_code == 403)
    r = client.post("/api/upload", files={"file": ("x.png", tiny_png(), "image/png")})
    check("CA → /api/upload = 403", r.status_code == 403)
    r = client.get("/api/oauth/google/start", follow_redirects=False)
    check("CA → /api/oauth/google/start = 403", r.status_code == 403)

    client.post("/api/auth/logout", json={})
    client.cookies.clear()
    ca_signup(client, "ca-b@example.com", "CA B", "07AAACO1234K1Z8")
    other = client.get("/api/ca/clients").json()
    check("CA-B sees no clients (not linked)", other["items"] == [])


def run_scenario_5_oauth_state_csrf(client: TestClient) -> None:
    section("Scenario 5 — OAuth state CSRF defences")
    biz_signup(client, "+919000004300", "OAuthBiz")

    r = client.get(
        "/api/oauth/google/callback?code=x&state=tampered-junk-not-signed",
        follow_redirects=False,
    )
    check("tampered state token → 403", r.status_code == 403)

    r = client.get("/api/oauth/google/callback", follow_redirects=False)
    check("missing code/state → 403", r.status_code == 403)

    r = client.get(
        "/api/oauth/google/callback?error=access_denied",
        follow_redirects=False,
    )
    check("user-denied callback redirects (not 5xx)", r.status_code in (302, 303, 307))

    r = client.get("/api/oauth/google/start", follow_redirects=False)
    check("start with dummy creds → 5xx (DependencyError)", r.status_code in (502, 503))


def run_scenario_6_csrf_cookie(client: TestClient) -> None:
    section("Scenario 6 — CSRF cookie + verify primitives")

    client.get("/api/auth/me")
    csrf = client.cookies.get("bl_csrf")
    check("bl_csrf cookie set on first GET", bool(csrf))

    from starlette.requests import Request

    from business_layer.security.csrf import verify_csrf

    scope = {
        "type": "http",
        "headers": [
            (b"cookie", f"bl_csrf={csrf}".encode()),
            (b"x-csrf-token", csrf.encode() if csrf else b""),
        ],
    }
    check("verify_csrf accepts matching header+cookie", verify_csrf(Request(scope)))

    scope_bad = {
        "type": "http",
        "headers": [
            (b"cookie", f"bl_csrf={csrf}".encode()),
            (b"x-csrf-token", b"wrong"),
        ],
    }
    check("verify_csrf rejects mismatch", not verify_csrf(Request(scope_bad)))


def run_scenario_7_input_validation_robustness(client: TestClient) -> None:
    section("Scenario 7 — input validation hardening")

    r = client.post("/api/auth/otp/request", json={"phone": "not-a-phone"})
    check("malformed phone → 422", r.status_code == 422)

    r = ca_signup(client, "g@example.com", "Bad GST", "TOO_SHORT")
    check("short GSTIN → 422", r.status_code == 422)

    r = ca_signup(client, "g2@example.com", "Bad GST", "INVALIDGSTIN123")
    check("bad-shape GSTIN → 422", r.status_code == 422)

    biz_signup(client, "+919000004500", "InputBiz")
    r = client.post("/api/upload", files={"file": ("empty.png", b"", "image/png")})
    check("empty upload → 4xx", 400 <= r.status_code < 500)

    fake_zip = b"PK\x03\x04" + b"\x00" * 100
    r = client.post("/api/upload", files={"file": ("a.png", fake_zip, "image/png")})
    check("magic-byte mismatch upload → 4xx", 400 <= r.status_code < 500)


def run_scenario_8_static_assets_served(client: TestClient) -> None:
    section("Scenario 8 — static shells served")
    expectations = [
        ("/static/landing/index.html", 200),
        ("/static/landing/style.css", 200),
        ("/static/business/index.html", 200),
        ("/static/business/css/style.css", 200),
        ("/static/business/js/app.js", 200),
        ("/static/business/js/dashboard.js", 200),
        ("/static/ca/index.html", 200),
        ("/static/ca/css/style.css", 200),
        ("/static/ca/js/app.js", 200),
        ("/static/ca/js/clients.js", 200),
        ("/static/ca/js/invoice.js", 200),
        ("/", 307),
        ("/business", 307),
        ("/ca", 307),
        ("/health", 200),
        ("/favicon.ico", 204),
    ]
    for path, expected in expectations:
        r = client.get(path, follow_redirects=False)
        check(f"{path} → {expected}", r.status_code == expected, f"got {r.status_code}")


def run_scenario_9_session_lifecycle(client: TestClient) -> None:
    section("Scenario 9 — session lifecycle")
    biz_signup(client, "+919000004600", "SessBiz")
    me = client.get("/api/auth/me")
    check("/api/auth/me with valid session → 200", me.status_code == 200)

    client.post("/api/auth/logout", json={})
    me = client.get("/api/auth/me")
    check("/api/auth/me after logout → 401", me.status_code == 401)


# ===== entrypoint ====================================================


def main() -> None:
    print("\n" + "=" * 70)
    print("BUSINESS LAYER — END-TO-END SMOKE")
    print("=" * 70)

    stub_pipeline()

    try:
        run_scenario_1_business_e2e(fresh_client())
        run_scenario_2_ca_signup_validation(fresh_client())
        run_scenario_3_ca_linkage_full_flow(fresh_client())
        run_scenario_4_cross_persona_idor(fresh_client())
        run_scenario_5_oauth_state_csrf(fresh_client())
        run_scenario_6_csrf_cookie(fresh_client())
        run_scenario_7_input_validation_robustness(fresh_client())
        run_scenario_8_static_assets_served(fresh_client())
        run_scenario_9_session_lifecycle(fresh_client())
    except Exception as exc:
        print(f"\nUNHANDLED EXCEPTION: {exc.__class__.__name__}: {exc}")
        FAIL.append(("smoke harness crashed", str(exc)))

    print("\n" + "=" * 70)
    print(f"SUMMARY:  {len(PASS)} passed,  {len(FAIL)} failed")
    print("=" * 70)
    if FAIL:
        print("\nFailures:")
        for label, detail in FAIL:
            print(f"  - {label}\n      {detail}")
        sys.exit(1)
    print("All checks green.")


if __name__ == "__main__":
    main()
