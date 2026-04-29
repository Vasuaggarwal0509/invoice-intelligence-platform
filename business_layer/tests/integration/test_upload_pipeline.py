"""End-to-end: OTP signup → upload → worker runs pipeline → invoice detail.

We don't run the REAL extraction pipeline here — it loads RapidOCR,
~1s on first call, flaky on CI. Instead we monkeypatch the
``PipelineRunner.run`` method to return deterministic stub results.
That still exercises:

* The upload route + size + MIME validation.
* inbox_messages / invoices / jobs transaction atomicity.
* The worker's drain-now synchronous path.
* pipeline_runs + validation_findings persistence.
* Invoice detail route + image route (workspace-gated).

Heavier tests that run the true pipeline against katanaml fixtures
are reserved for the ``ocr_heavy`` / ``dataset_heavy`` markers, kept
out of the default suite.
"""

from __future__ import annotations

import logging
import re
import struct
import zlib

import pytest

PHONE = "+919000000121"


# ---------- helpers ----------------------------------------------------


def _tiny_png_bytes(width: int = 4, height: int = 4) -> bytes:
    """Return a valid PNG for a ``width``×``height`` white image.

    We hand-roll the bytes so tests run without Pillow needing to
    encode — isolates failure modes strictly to business_layer code.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_chunk = _png_chunk(b"IHDR", ihdr)
    # Each row: filter byte + 3 bytes per pixel.
    row = b"\x00" + b"\xff\xff\xff" * width
    raw = row * height
    compressed = zlib.compress(raw)
    idat_chunk = _png_chunk(b"IDAT", compressed)
    iend_chunk = _png_chunk(b"IEND", b"")
    return sig + ihdr_chunk + idat_chunk + iend_chunk


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def _otp_from_logs(phone: str, caplog: pytest.LogCaptureFixture) -> str:
    pat = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for rec in reversed(caplog.records):
        m = pat.search(rec.getMessage())
        if m:
            return m.group(1)
    raise AssertionError("OTP plaintext not captured")


def _sign_up_and_login(test_client, caplog: pytest.LogCaptureFixture) -> None:
    """Run the OTP flow inline so downstream tests can assume a session."""
    caplog.set_level(logging.INFO, logger="business_layer.routes.auth")
    test_client.post("/api/auth/otp/request", json={"phone": PHONE})
    code = _otp_from_logs(PHONE, caplog)
    r = test_client.post(
        "/api/auth/otp/verify",
        json={"phone": PHONE, "code": code, "display_name": "Test Co"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture
def stubbed_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap ``PipelineRunner.run`` for a deterministic stub.

    Returns (OCRResult-ish, ExtractionResult-ish, TableExtractionResult-ish,
    ValidationResult-ish) — but we only need the shape the
    extraction_runner reads: ``.model_dump_json()`` on each, plus
    ``extraction_result.fields`` and
    ``validation_result.findings``.
    """
    from extraction_layer.components.extraction.types import (
        ExtractedField,
        ExtractionResult,
    )
    from extraction_layer.components.ocr.types import OCRResult, PageSize
    from extraction_layer.components.tables.types import TableExtractionResult
    from extraction_layer.components.validation.types import (
        RuleFinding,
        RuleOutcome,
        ValidationResult,
    )

    def _fake_run(self, image):  # type: ignore[no-untyped-def]
        ocr = OCRResult(
            tokens=[],
            lines=[],
            page=PageSize(width=4, height=4),
            backend="stub",
            duration_ms=0.5,
        )
        extraction = ExtractionResult(
            fields={
                "seller": ExtractedField(
                    name="seller", value="Stub Vendor Pvt Ltd", confidence=0.9, source="stub"
                ),
                "invoice_no": ExtractedField(
                    name="invoice_no", value="INV-001", confidence=0.9, source="stub"
                ),
                "invoice_date": ExtractedField(
                    name="invoice_date", value="2026-04-22", confidence=0.9, source="stub"
                ),
            },
            extractor="stub",
            duration_ms=0.2,
        )
        tables = TableExtractionResult(
            items=[],
            extractor="stub",
            duration_ms=0.1,
        )
        validation = ValidationResult(
            findings=[
                RuleFinding(
                    rule_name="test_pass",
                    target="invoice_no",
                    outcome=RuleOutcome.PASS,
                    reason="stub",
                ),
            ],
        )
        return ocr, extraction, tables, validation

    # Reset the cached pipeline singleton so our stub wires in for this test.
    import business_layer.services.extraction_runner as er

    er._pipeline_singleton = None
    monkeypatch.setattr(
        "extraction_layer.backend.app.pipeline.PipelineRunner.run",
        _fake_run,
    )


# ---------- tests ------------------------------------------------------


class TestUploadFlow:
    """The Sprint 2 gate — upload, process, view detail."""

    def test_upload_then_detail_roundtrip(
        self,
        test_client,
        caplog: pytest.LogCaptureFixture,
        stubbed_pipeline,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]
        _sign_up_and_login(test_client, caplog)

        png = _tiny_png_bytes()
        r = test_client.post(
            "/api/upload",
            files={"file": ("tiny.png", png, "image/png")},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        invoice_id = body["invoice_id"]
        assert invoice_id
        assert body["status"] == "queued"

        # Drive the worker inline so the assertion is synchronous.
        from business_layer.workers.extraction_worker import drain_now

        count = drain_now()
        assert count >= 1

        # Detail must now carry extracted fields.
        detail = test_client.get(f"/api/invoices/{invoice_id}")
        assert detail.status_code == 200
        doc = detail.json()
        assert doc["invoice"]["vendor_name"] == "Stub Vendor Pvt Ltd"
        assert doc["invoice"]["invoice_no"] == "INV-001"
        assert doc["invoice"]["extraction_status"] == "extracted"
        # Findings counts reflect the 1 PASS we stubbed.
        assert doc["invoice"]["findings_summary"]["pass"] == 1
        assert doc["invoice"]["findings_summary"]["fail"] == 0

        # Image route serves the bytes we uploaded.
        img = test_client.get(f"/api/invoices/{invoice_id}/image")
        assert img.status_code == 200
        assert img.headers["content-type"].startswith("image/png")
        assert img.content == png

        # Inbox listing shows the new row as 'extracted'.
        inbox = test_client.get("/api/inbox")
        assert inbox.status_code == 200
        items = inbox.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "extracted"
        assert items[0]["vendor_name"] == "Stub Vendor Pvt Ltd"

    def test_upload_requires_auth(self, test_client) -> None:  # type: ignore[no-untyped-def]
        png = _tiny_png_bytes()
        r = test_client.post(
            "/api/upload",
            files={"file": ("t.png", png, "image/png")},
        )
        assert r.status_code == 401

    def test_duplicate_upload_deduped_by_sha(
        self,
        test_client,
        caplog: pytest.LogCaptureFixture,
        stubbed_pipeline,
    ) -> None:  # type: ignore[no-untyped-def]
        _sign_up_and_login(test_client, caplog)
        png = _tiny_png_bytes()

        r1 = test_client.post("/api/upload", files={"file": ("a.png", png, "image/png")})
        r2 = test_client.post("/api/upload", files={"file": ("b.png", png, "image/png")})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["inbox_message_id"] == r2.json()["inbox_message_id"]
        assert r2.json()["was_duplicate"] is True
