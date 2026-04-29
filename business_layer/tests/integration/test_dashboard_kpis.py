"""Integration tests for Sprint 3: business dashboard KPIs.

Seeds invoice rows directly via the repository layer rather than
running real uploads, so the tests exercise KPI math independently
of extraction-pipeline timing. The route is still hit end-to-end
(through FastAPI) so serialisation + workspace scoping are covered.
"""

from __future__ import annotations

import logging
import re

import pytest


def _otp_from_logs(phone: str, caplog: pytest.LogCaptureFixture) -> str:
    pat = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for rec in reversed(caplog.records):
        m = pat.search(rec.getMessage())
        if m:
            return m.group(1)
    raise AssertionError("OTP plaintext not captured")


def _login_as(test_client, phone: str, caplog: pytest.LogCaptureFixture, name: str) -> str:
    """Sign up (or log in) via OTP. Returns the workspace id."""
    caplog.set_level(logging.INFO, logger="business_layer.routes.auth")
    test_client.post("/api/auth/otp/request", json={"phone": phone})
    code = _otp_from_logs(phone, caplog)
    r = test_client.post(
        "/api/auth/otp/verify",
        json={"phone": phone, "code": code, "display_name": name},
    )
    assert r.status_code == 200, r.text
    return r.json()["workspace"]["id"]


def _seed_invoices(workspace_id: str, rows: list[dict]) -> None:
    """Insert invoice rows directly — bypassing extraction + upload plumbing.

    Each row dict may carry: ``vendor_name``, ``total_amount_minor``,
    ``failing_rules`` (default 0), ``created_at_offset_days`` (default 0,
    relative to now), ``invoice_no``, ``invoice_date``.
    """
    from business_layer.db import get_session
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
        validation_findings as t_vf,
    )
    from business_layer.repositories._ids import new_id, now_ms

    # Need a source row so inbox_messages FK is satisfied.
    with get_session() as s:
        # 1) source
        source_id = new_id()
        s.execute(
            t_sources.insert().values(
                id=source_id,
                workspace_id=workspace_id,
                kind="upload",
                label="test",
                status="connected",
                default_extraction_mode="instant",
                last_polled_at=None,
                created_at=now_ms(),
            )
        )

        for idx, row in enumerate(rows):
            offset_days = row.get("created_at_offset_days", 0)
            created = now_ms() + offset_days * 24 * 3600 * 1000
            inbox_id = new_id()
            invoice_id = row.get("invoice_id") or new_id()

            s.execute(
                t_inbox.insert().values(
                    id=inbox_id,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    external_id=None,
                    sender=None,
                    subject=f"test-{idx}.png",
                    received_at=created,
                    content_type="image/png",
                    file_storage_key=f"test/{idx}.png",
                    file_size_bytes=100,
                    file_sha256=new_id(),  # doesn't matter, just unique
                    status="extracted",
                    ignored_reason=None,
                    created_at=created,
                )
            )
            s.execute(
                t_invoices.insert().values(
                    id=invoice_id,
                    workspace_id=workspace_id,
                    inbox_message_id=inbox_id,
                    vendor_name=row.get("vendor_name"),
                    client_name=None,
                    client_gstin=None,
                    seller_gstin=None,
                    invoice_no=row.get("invoice_no"),
                    invoice_date=row.get("invoice_date"),
                    total_amount_minor=row.get("total_amount_minor"),
                    currency="INR",
                    status="pending",
                    created_at=created,
                    approved_at=None,
                    approved_by_user_id=None,
                )
            )
            for i in range(row.get("failing_rules", 0)):
                s.execute(
                    t_vf.insert().values(
                        id=new_id(),
                        workspace_id=workspace_id,
                        invoice_id=invoice_id,
                        rule_name=f"test_rule_{i}",
                        target="something",
                        outcome="FAIL",
                        reason="seeded fail",
                        expected=None,
                        observed=None,
                        created_at=created,
                    )
                )


# ---------- tests ------------------------------------------------------


class TestDashboardKpis:
    def test_empty_workspace_returns_zero_tiles(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        _login_as(test_client, "+919000001001", caplog, "Empty Co")
        r = test_client.get("/api/business/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["currency"] == "INR"
        assert body["tiles"] == {
            "invoices_this_month": 0,
            "total_spend_minor": 0,
            "itc_estimate_minor": 0,
            "needs_review_count": 0,
        }
        assert body["top_vendors"] == []
        assert body["needs_review"] == []

    def test_tiles_aggregate_correctly(self, test_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
        workspace_id = _login_as(test_client, "+919000001002", caplog, "Acme")
        _seed_invoices(
            workspace_id,
            [
                # 3 clean invoices this month: 100.00 + 200.00 + 50.00 = 350.00
                {"vendor_name": "Vendor A", "total_amount_minor": 10_000},
                {"vendor_name": "Vendor A", "total_amount_minor": 20_000},
                {"vendor_name": "Vendor B", "total_amount_minor": 5_000},
                # 1 with a failing rule — excluded from ITC, contributes to needs-review:
                {"vendor_name": "Vendor B", "total_amount_minor": 10_000, "failing_rules": 2},
            ],
        )
        r = test_client.get("/api/business/dashboard")
        assert r.status_code == 200
        tiles = r.json()["tiles"]
        assert tiles["invoices_this_month"] == 4
        assert tiles["total_spend_minor"] == 45_000
        # ITC = sum of CLEAN totals * 18 // 118 = 35_000 * 18 // 118 = 5_338 (integer truncation)
        assert tiles["itc_estimate_minor"] == 35_000 * 18 // 118
        assert tiles["needs_review_count"] == 1

    def test_top_vendors_sorted_by_spend(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        workspace_id = _login_as(test_client, "+919000001003", caplog, "Sorted")
        _seed_invoices(
            workspace_id,
            [
                {"vendor_name": "Alpha", "total_amount_minor": 10_000},
                {"vendor_name": "Beta", "total_amount_minor": 100_000},
                {"vendor_name": "Beta", "total_amount_minor": 50_000},
                {"vendor_name": "Gamma", "total_amount_minor": 75_000},
            ],
        )
        r = test_client.get("/api/business/dashboard")
        assert r.status_code == 200
        vendors = r.json()["top_vendors"]
        names = [v["vendor_name"] for v in vendors]
        # Beta: 150k, Gamma: 75k, Alpha: 10k
        assert names == ["Beta", "Gamma", "Alpha"]
        beta = vendors[0]
        assert beta["invoice_count"] == 2
        assert beta["total_minor"] == 150_000

    def test_top_vendors_excludes_unextracted(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        workspace_id = _login_as(test_client, "+919000001004", caplog, "Null Co")
        _seed_invoices(
            workspace_id,
            [
                {"vendor_name": None, "total_amount_minor": 10_000},  # not yet extracted
                {"vendor_name": "Alpha", "total_amount_minor": 5_000},
            ],
        )
        r = test_client.get("/api/business/dashboard")
        vendors = r.json()["top_vendors"]
        assert len(vendors) == 1
        assert vendors[0]["vendor_name"] == "Alpha"

    def test_needs_review_lists_failing_invoices(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        workspace_id = _login_as(test_client, "+919000001005", caplog, "Needs")
        _seed_invoices(
            workspace_id,
            [
                {
                    "vendor_name": "V",
                    "total_amount_minor": 1_000,
                    "failing_rules": 3,
                    "invoice_no": "INV-1",
                },
                {
                    "vendor_name": "V",
                    "total_amount_minor": 2_000,
                    "failing_rules": 0,
                    "invoice_no": "INV-2",
                },
                {
                    "vendor_name": "V",
                    "total_amount_minor": 3_000,
                    "failing_rules": 1,
                    "invoice_no": "INV-3",
                },
            ],
        )
        r = test_client.get("/api/business/dashboard")
        needs_review = r.json()["needs_review"]
        invoice_nos = [i["invoice_no"] for i in needs_review]
        assert "INV-1" in invoice_nos
        assert "INV-3" in invoice_nos
        assert "INV-2" not in invoice_nos
        inv1 = next(i for i in needs_review if i["invoice_no"] == "INV-1")
        assert inv1["failing_rules"] == 3


class TestDashboardSecurity:
    """Cross-workspace isolation on the new endpoint."""

    def test_requires_authentication(self, test_client) -> None:  # type: ignore[no-untyped-def]
        r = test_client.get("/api/business/dashboard")
        assert r.status_code == 401

    def test_one_workspace_cannot_see_another_workspaces_kpis(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        ws_a = _login_as(test_client, "+919000001100", caplog, "WS-A")
        _seed_invoices(
            ws_a,
            [
                {"vendor_name": "Leak", "total_amount_minor": 999_999},
            ],
        )
        test_client.post("/api/auth/logout", json={})
        test_client.cookies.clear()
        caplog.clear()
        _login_as(test_client, "+919000001101", caplog, "WS-B")
        r = test_client.get("/api/business/dashboard")
        body = r.json()
        assert body["tiles"]["invoices_this_month"] == 0
        assert body["tiles"]["total_spend_minor"] == 0
        assert body["top_vendors"] == []  # leaked row must not surface
