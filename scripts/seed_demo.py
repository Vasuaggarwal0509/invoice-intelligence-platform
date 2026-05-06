"""Seed the local SQLite DB with a demo cast for visualizing dashboards.

Creates:
  * 1 CA firm workspace (Mehta & Associates) — login: ca@demo.local / demoCApass1234
  * 4 business workspaces, all linked to the CA via ``ca_gstin``
  * ~25 invoices spread across April + May 2026, mostly clean with a
    handful of FAIL findings so the "needs review" tile populates
  * One placeholder PNG per invoice rendered with the vendor / total /
    invoice no so the detail view shows something real

Idempotent: every seeded row carries the audit tag ``seed:demo``. The
script wipes those rows (and *only* those rows) before re-inserting,
so re-running it never duplicates and never touches real data.

Run with::

    make seed
    # or directly:
    python -m scripts.seed_demo
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import random
import sys
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, insert, select

from business_layer.db import engine as db_engine
from business_layer.db.tables import (
    events as t_events,
)
from business_layer.db.tables import (
    inbox_messages as t_inbox,
)
from business_layer.db.tables import (
    invoices as t_invoices,
)
from business_layer.db.tables import (
    sources as t_sources,
)
from business_layer.db.tables import (
    users as t_users,
)
from business_layer.db.tables import (
    validation_findings as t_vf,
)
from business_layer.db.tables import (
    workspaces as t_workspaces,
)
from business_layer.repositories._ids import new_id, now_ms
from business_layer.security import passwords as pw
from business_layer.services import storage

_log = logging.getLogger("seed_demo")

SEED_TAG = "seed:demo"

CA_GSTIN = "22MEHTA0000A1Z5"
CA_EMAIL = "ca@mehta.in"
CA_PASSWORD = "demoCApass1234"
CA_DISPLAY = "Mehta & Associates"


@dataclass(frozen=True)
class BusinessSpec:
    name: str
    phone: str
    gstin: str
    vendors: list[str]


BUSINESSES: list[BusinessSpec] = [
    BusinessSpec(
        name="Aarav Trading Co.",
        phone="+919900000001",
        gstin="27ABCDE1234F1Z5",
        vendors=["Reliance Retail Ltd", "BSNL", "Asian Paints", "Blue Dart Express"],
    ),
    BusinessSpec(
        name="Bharat Logistics",
        phone="+919900000002",
        gstin="29BCDEF2345G2Z6",
        vendors=["IndianOil Corp", "Tata Steel", "Apollo Tyres", "MRF Ltd"],
    ),
    BusinessSpec(
        name="Chitra Boutique",
        phone="+919900000003",
        gstin="33CDEFG3456H3Z7",
        vendors=["Amazon Business", "JioFiber", "Adobe Systems India", "Zerodha Broking"],
    ),
    BusinessSpec(
        name="Deepak Manufacturing",
        phone="+919900000004",
        gstin="24DEFGH4567I4Z8",
        vendors=["Larsen & Toubro", "Bosch Ltd", "BHEL", "Siemens India"],
    ),
]

# Two-month window: April + May 2026 (current date in this project is 2026-05-06).
# Each invoice gets a created_at inside this window. We build a few per business,
# spread across both months so the "this month" + "last month" toggles both fill.
PERIODS = [
    (2026, 4),  # April
    (2026, 5),  # May
]


# ---------------------------------------------------------------------- helpers


def _ms_for(year: int, month: int, day: int, hour: int = 11) -> int:
    """UTC-ms timestamp for a calendar moment — used for created_at fields."""
    return int(dt.datetime(year, month, day, hour, 0, tzinfo=dt.UTC).timestamp() * 1000)


def _render_invoice_png(
    *,
    workspace_name: str,
    vendor_name: str,
    invoice_no: str,
    invoice_date: str,
    total_inr: float,
) -> bytes:
    """Render a tiny placeholder PNG that *looks* like an invoice line.

    Not real OCR fodder — purely a visual stand-in so the user opening
    an invoice detail page sees something rather than a 404 image.
    """
    img = Image.new("RGB", (560, 360), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_b = ImageFont.truetype("DejaVuSans.ttf", 16)
        font_s = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:  # pragma: no cover — falls back when fonts not present
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()
        font_s = ImageFont.load_default()

    draw.rectangle([(0, 0), (560, 50)], fill=(40, 80, 160))
    draw.text((20, 14), vendor_name, fill=(255, 255, 255), font=font_h)

    draw.text((20, 70), f"Bill to: {workspace_name}", fill=(60, 60, 60), font=font_b)
    draw.text((20, 100), f"Invoice no: {invoice_no}", fill=(20, 20, 20), font=font_b)
    draw.text((20, 128), f"Date: {invoice_date}", fill=(20, 20, 20), font=font_b)

    draw.line([(20, 170), (540, 170)], fill=(220, 220, 220), width=1)
    draw.text(
        (20, 190), "Description: Goods / services as per agreement", fill=(50, 50, 50), font=font_s
    )
    draw.text((20, 215), "GST @ 18% (inclusive)", fill=(50, 50, 50), font=font_s)
    draw.line([(20, 260), (540, 260)], fill=(220, 220, 220), width=1)

    draw.text((20, 280), "Total payable", fill=(20, 20, 20), font=font_b)
    draw.text(
        (380, 278),
        f"Rs {total_inr:,.2f}",
        fill=(40, 80, 160),
        font=font_h,
    )

    draw.text(
        (20, 330),
        "Demo placeholder · seeded by scripts/seed_demo.py",
        fill=(150, 150, 150),
        font=font_s,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------------ wipe


def _wipe_seed_rows(session) -> None:  # type: ignore[no-untyped-def]
    """Delete every row previously inserted by this seed.

    Strategy: each row we insert also writes an ``events`` audit row
    with ``metadata.seed = 'seed:demo'``. We collect the workspace_ids
    from those events, then cascade-delete starting at workspaces
    (FKs on inbox_messages, invoices, etc. are CASCADE → ON DELETE).
    """
    seed_ws_ids: set[str] = set()
    rows = session.execute(select(t_events.c.metadata_json, t_events.c.workspace_id)).all()
    for meta_json, ws_id in rows:
        if not meta_json or not ws_id:
            continue
        try:
            meta = json.loads(meta_json)
        except Exception:
            continue
        if meta.get("seed") == SEED_TAG:
            seed_ws_ids.add(ws_id)

    if not seed_ws_ids:
        return

    # Find owner_user_ids first (we want to clean those up too).
    owners = session.execute(
        select(t_workspaces.c.owner_user_id).where(t_workspaces.c.id.in_(seed_ws_ids))
    ).all()
    owner_ids = [r.owner_user_id for r in owners]

    # Cascade is set up on workspaces → inbox/invoices/sources etc.
    session.execute(delete(t_workspaces).where(t_workspaces.c.id.in_(seed_ws_ids)))
    if owner_ids:
        session.execute(delete(t_users).where(t_users.c.id.in_(owner_ids)))
    # Events themselves are not cascade-linked to workspaces — clean by tag.
    seed_event_ids = []
    rows = session.execute(select(t_events.c.id, t_events.c.metadata_json)).all()
    for ev_id, meta_json in rows:
        if not meta_json:
            continue
        try:
            meta = json.loads(meta_json)
        except Exception:
            continue
        if meta.get("seed") == SEED_TAG:
            seed_event_ids.append(ev_id)
    if seed_event_ids:
        session.execute(delete(t_events).where(t_events.c.id.in_(seed_event_ids)))


# ----------------------------------------------------------------- inserts


def _insert_event(session, *, workspace_id: str, action: str, metadata: dict) -> None:  # type: ignore[no-untyped-def]
    metadata = {**metadata, "seed": SEED_TAG}
    session.execute(
        insert(t_events).values(
            id=new_id(),
            workspace_id=workspace_id,
            actor_user_id=None,
            action=action,
            target_type=None,
            target_id=None,
            metadata_json=json.dumps(metadata, separators=(",", ":")),
            ts=now_ms(),
        )
    )


def _insert_user(  # type: ignore[no-untyped-def]
    session,
    *,
    role: str,
    display_name: str,
    phone: str | None = None,
    email: str | None = None,
    password_hash: str | None = None,
) -> str:
    uid = new_id()
    session.execute(
        insert(t_users).values(
            id=uid,
            role=role,
            phone=phone,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            created_at=now_ms(),
            failed_login_count=0,
        )
    )
    return uid


def _insert_workspace(  # type: ignore[no-untyped-def]
    session,
    *,
    owner_user_id: str,
    name: str,
    gstin: str,
    ca_gstin: str | None,
) -> str:
    wid = new_id()
    session.execute(
        insert(t_workspaces).values(
            id=wid,
            owner_user_id=owner_user_id,
            name=name,
            gstin=gstin,
            created_via="self_signup",
            tier="free",
            status="active",
            default_extraction_mode="instant",
            ca_gstin=ca_gstin,
            created_at=now_ms(),
        )
    )
    return wid


def _insert_upload_source(session, *, workspace_id: str) -> str:  # type: ignore[no-untyped-def]
    sid = new_id()
    session.execute(
        insert(t_sources).values(
            id=sid,
            workspace_id=workspace_id,
            kind="upload",
            label="Manual upload",
            status="connected",
            default_extraction_mode="instant",
            credentials_encrypted=None,
            last_polled_at=None,
            created_at=now_ms(),
        )
    )
    return sid


def _insert_invoice_with_blob(  # type: ignore[no-untyped-def]
    session,
    *,
    workspace_id: str,
    workspace_name: str,
    source_id: str,
    vendor_name: str,
    seller_gstin: str,
    invoice_no: str,
    invoice_date: str,  # ISO yyyy-mm-dd
    total_minor: int,
    created_ms: int,
    findings: list[dict],
    status: str = "approved",
) -> str:
    """Create the inbox_message + invoice + findings + on-disk blob.

    Returns the invoice id.
    """
    png_bytes = _render_invoice_png(
        workspace_name=workspace_name,
        vendor_name=vendor_name,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        total_inr=total_minor / 100.0,
    )
    storage_key, sha = storage.store_blob(
        workspace_id=workspace_id,
        data=png_bytes,
        content_type="image/png",
    )

    inbox_id = new_id()
    session.execute(
        insert(t_inbox).values(
            id=inbox_id,
            workspace_id=workspace_id,
            source_id=source_id,
            external_id=None,
            sender=None,
            subject=f"{vendor_name} — {invoice_no}",
            received_at=created_ms,
            content_type="image/png",
            file_storage_key=storage_key,
            file_size_bytes=len(png_bytes),
            file_sha256=sha,
            status="extracted",
            ignored_reason=None,
            created_at=created_ms,
        )
    )

    inv_id = new_id()
    session.execute(
        insert(t_invoices).values(
            id=inv_id,
            workspace_id=workspace_id,
            inbox_message_id=inbox_id,
            vendor_name=vendor_name,
            client_name=workspace_name,
            client_gstin=None,
            seller_gstin=seller_gstin,
            invoice_no=invoice_no,
            invoice_date=invoice_date,
            total_amount_minor=total_minor,
            currency="INR",
            status=status,
            created_at=created_ms,
            approved_at=created_ms if status == "approved" else None,
            approved_by_user_id=None,
        )
    )

    if findings:
        session.execute(
            insert(t_vf),
            [
                {
                    "id": new_id(),
                    "workspace_id": workspace_id,
                    "invoice_id": inv_id,
                    "rule_name": f["rule_name"],
                    "target": f.get("target"),
                    "outcome": f["outcome"],
                    "reason": f.get("reason"),
                    "expected": f.get("expected"),
                    "observed": f.get("observed"),
                    "created_at": created_ms,
                }
                for f in findings
            ],
        )

    return inv_id


# ------------------------------------------------------------------ build


def _gstin_for_vendor(vendor_idx: int, business_idx: int) -> str:
    """Deterministic dummy seller GSTIN per vendor — distinct, format-valid-ish."""
    state = ["07", "27", "29", "33", "24", "06"][business_idx % 6]
    seq = f"{(vendor_idx * 13 + business_idx * 7) % 9999:04d}"
    return f"{state}AAAAA{seq}A1Z5"


def _build_invoices_for(
    *,
    business_idx: int,
    spec: BusinessSpec,
) -> list[dict]:
    """Plan invoice rows for one business — half clean, ~1–2 with FAIL findings."""
    rng = random.Random(1000 + business_idx)
    plan: list[dict] = []
    target_count = rng.choice([5, 6, 7])
    fail_indices = {
        rng.randrange(0, target_count),  # one guaranteed FAIL
    }
    if rng.random() < 0.4:
        fail_indices.add(rng.randrange(0, target_count))

    # Force the first half of invoices into April and the rest into May so
    # the dashboard's period switcher always has data on both sides — a
    # purely-random distribution sometimes lands every invoice in one
    # month for small N.
    for i in range(target_count):
        year, month = PERIODS[0] if i < target_count // 2 else PERIODS[1]
        day = rng.randint(2, 26)
        hour = rng.randint(9, 19)
        vendor = spec.vendors[i % len(spec.vendors)]
        amount_rupees = rng.choice(
            [2150, 4990, 8400, 12750, 28999, 49500, 87600, 142300, 312500, 489900]
        )
        amount_minor = amount_rupees * 100 + rng.randint(0, 99)
        invoice_no = f"INV-{year % 100}{month:02d}-{business_idx:02d}{i:02d}"

        findings: list[dict] = []
        if i in fail_indices:
            kind = rng.choice(["gstin_format", "tax_math", "missing_hsn"])
            if kind == "gstin_format":
                findings.append(
                    {
                        "rule_name": "gstin_format",
                        "target": "seller_gstin",
                        "outcome": "FAIL",
                        "reason": "GSTIN checksum failed",
                        "expected": "valid 15-char GSTIN",
                        "observed": "27ABCDE1234F1ZX",  # deliberate bad checksum
                    }
                )
            elif kind == "tax_math":
                findings.append(
                    {
                        "rule_name": "tax_math",
                        "target": "totals",
                        "outcome": "FAIL",
                        "reason": "CGST + SGST does not match 18% of taxable",
                        "expected": "tax = 18% taxable ± ₹1",
                        "observed": "tax differs by ₹14",
                    }
                )
            else:
                findings.append(
                    {
                        "rule_name": "hsn_lookup",
                        "target": "line_items",
                        "outcome": "FAIL",
                        "reason": "Line item missing HSN code",
                        "expected": "HSN present on every line",
                        "observed": "1 of 3 lines blank",
                    }
                )
        # always add one PASS rule so detail view has something
        findings.append(
            {
                "rule_name": "duplicate_check",
                "target": "invoice_no",
                "outcome": "PASS",
                "reason": "no other invoice in workspace shares this number",
            }
        )

        plan.append(
            {
                "vendor": vendor,
                "vendor_idx": i,
                "invoice_no": invoice_no,
                "amount_minor": amount_minor,
                "year": year,
                "month": month,
                "day": day,
                "hour": hour,
                "findings": findings,
            }
        )
    return plan


# ---------------------------------------------------------------------- main


def run_seed() -> None:
    """Orchestrate the seed end-to-end."""
    db_engine.init_db()
    with db_engine.get_session() as session:
        _wipe_seed_rows(session)

        # --- CA workspace ------------------------------------------------
        ca_user_id = _insert_user(
            session,
            role="ca",
            display_name=CA_DISPLAY,
            email=CA_EMAIL,
            password_hash=pw.hash_password(CA_PASSWORD),
        )
        ca_ws_id = _insert_workspace(
            session,
            owner_user_id=ca_user_id,
            name=CA_DISPLAY,
            gstin=CA_GSTIN,
            ca_gstin=None,  # CAs don't have a CA themselves
        )
        _insert_event(
            session,
            workspace_id=ca_ws_id,
            action="seed.ca_workspace",
            metadata={"email": CA_EMAIL},
        )

        # --- 4 business workspaces + invoices ---------------------------
        total_invoices = 0
        total_failed = 0
        for idx, spec in enumerate(BUSINESSES):
            biz_user_id = _insert_user(
                session,
                role="business",
                display_name=spec.name,
                phone=spec.phone,
            )
            biz_ws_id = _insert_workspace(
                session,
                owner_user_id=biz_user_id,
                name=spec.name,
                gstin=spec.gstin,
                ca_gstin=CA_GSTIN,
            )
            _insert_event(
                session,
                workspace_id=biz_ws_id,
                action="seed.business_workspace",
                metadata={"phone": spec.phone, "gstin": spec.gstin},
            )

            source_id = _insert_upload_source(session, workspace_id=biz_ws_id)

            for plan in _build_invoices_for(business_idx=idx, spec=spec):
                created_ms = _ms_for(plan["year"], plan["month"], plan["day"], plan["hour"])
                _insert_invoice_with_blob(
                    session,
                    workspace_id=biz_ws_id,
                    workspace_name=spec.name,
                    source_id=source_id,
                    vendor_name=plan["vendor"],
                    seller_gstin=_gstin_for_vendor(plan["vendor_idx"], idx),
                    invoice_no=plan["invoice_no"],
                    invoice_date=f"{plan['year']:04d}-{plan['month']:02d}-{plan['day']:02d}",
                    total_minor=plan["amount_minor"],
                    created_ms=created_ms,
                    findings=plan["findings"],
                )
                total_invoices += 1
                if any(f["outcome"] == "FAIL" for f in plan["findings"]):
                    total_failed += 1

        print()
        print("Seed complete.")
        print(f"  CA workspace : {CA_DISPLAY} (gstin={CA_GSTIN})")
        print(f"  CA login     : email={CA_EMAIL}  password={CA_PASSWORD}")
        print(f"  Businesses   : {len(BUSINESSES)} (all linked via ca_gstin={CA_GSTIN})")
        for spec in BUSINESSES:
            print(f"    - {spec.name}  phone={spec.phone}  gstin={spec.gstin}")
        print(f"  Invoices     : {total_invoices} ({total_failed} with FAIL findings)")
        print("  Period       : Apr–May 2026")
        print()
        print("Business login flow: phone → OTP visible in server logs as DEV_OTP_ISSUED.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        run_seed()
    except Exception:
        _log.exception("seed failed")
        sys.exit(1)
