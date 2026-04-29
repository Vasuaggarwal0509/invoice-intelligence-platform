"""Security tests for Sprint 2: upload + invoice detail.

Covers:
* Oversized payload rejection (validator before extraction).
* Bad MIME / magic-byte mismatch rejection.
* IDOR — another workspace cannot read my invoice detail or image.
"""

from __future__ import annotations

import logging
import re
import struct
import zlib

import pytest


def _tiny_png_bytes() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    ihdr_chunk = _chunk(b"IHDR", ihdr)
    raw = (b"\x00" + b"\xff\xff\xff" * 2) * 2
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr_chunk + idat + iend


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _otp_from_logs(phone: str, caplog: pytest.LogCaptureFixture) -> str:
    pat = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for rec in reversed(caplog.records):
        m = pat.search(rec.getMessage())
        if m:
            return m.group(1)
    raise AssertionError("OTP plaintext not captured")


def _login_as(test_client, phone: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="business_layer.routes.auth")
    test_client.post("/api/auth/otp/request", json={"phone": phone})
    code = _otp_from_logs(phone, caplog)
    r = test_client.post(
        "/api/auth/otp/verify",
        json={"phone": phone, "code": code, "display_name": f"WS-{phone[-3:]}"},
    )
    assert r.status_code == 200


class TestUploadRejections:
    def test_non_image_bytes_rejected(self, test_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
        _login_as(test_client, "+919000000200", caplog)
        r = test_client.post(
            "/api/upload",
            files={"file": ("e.txt", b"hello world not an image", "text/plain")},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_failed"

    def test_empty_upload_rejected(self, test_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
        _login_as(test_client, "+919000000201", caplog)
        r = test_client.post(
            "/api/upload",
            files={"file": ("e.png", b"", "image/png")},
        )
        assert r.status_code == 422

    def test_lied_about_content_type_still_rejected(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        """Client sends Content-Type image/png but bytes are a text file.

        We don't trust the header — magic-byte sniff decides.
        """
        _login_as(test_client, "+919000000202", caplog)
        r = test_client.post(
            "/api/upload",
            files={"file": ("fake.png", b"PK\x03\x04not a png", "image/png")},
        )
        assert r.status_code == 422

    def test_oversized_upload_rejected(
        self,
        test_client,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:  # type: ignore[no-untyped-def]
        _login_as(test_client, "+919000000203", caplog)
        # Force size limit to the smallest valid value (>=1024 per the
        # Settings validator) so the test doesn't generate 25 MB.
        monkeypatch.setenv("PLATFORM_UPLOAD_MAX_BYTES", "2048")
        from business_layer.config import get_settings

        get_settings.cache_clear()

        # Build a blob larger than the new cap, starting with a PNG
        # magic prefix so the content-type sniff passes and the size
        # check is what fires.
        blob = _tiny_png_bytes() + b"\x00" * 4096
        assert len(blob) > 2048
        r = test_client.post(
            "/api/upload",
            files={"file": ("big.png", blob, "image/png")},
        )
        assert r.status_code == 422
        assert "exceeds" in (r.json().get("detail") or "").lower()


class TestInvoiceIdor:
    """Cross-workspace reads must 404 — not 403."""

    def test_another_workspace_cannot_read_my_invoice(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        # Stub the pipeline so the upload actually produces an invoice.
        import business_layer.services.extraction_runner as er
        from extraction_layer.components.extraction.types import ExtractionResult
        from extraction_layer.components.ocr.types import OCRResult, PageSize
        from extraction_layer.components.tables.types import TableExtractionResult

        def _fake_run(self, image):  # type: ignore[no-untyped-def]
            return (
                OCRResult(
                    tokens=[],
                    lines=[],
                    page=PageSize(width=2, height=2),
                    backend="stub",
                    duration_ms=0.1,
                ),
                ExtractionResult(fields={}, extractor="stub", duration_ms=0.1),
                TableExtractionResult(items=[], extractor="stub", duration_ms=0.1),
                None,
            )

        import extraction_layer.backend.app.pipeline as pl

        original = pl.PipelineRunner.run
        pl.PipelineRunner.run = _fake_run  # type: ignore[assignment]
        # Reset cached pipeline singleton inside extraction_runner so the
        # stub takes effect for this test's fresh pipeline construction.
        er._pipeline_singleton = None

        try:
            # Workspace A — upload an invoice.
            _login_as(test_client, "+919000000301", caplog)
            png = _tiny_png_bytes()
            up = test_client.post("/api/upload", files={"file": ("i.png", png, "image/png")})
            assert up.status_code == 201
            invoice_id_a = up.json()["invoice_id"]

            from business_layer.workers.extraction_worker import drain_now

            drain_now()

            # Log out A, sign up as Workspace B.
            test_client.post("/api/auth/logout", json={})
            test_client.cookies.clear()
            caplog.clear()
            _login_as(test_client, "+919000000302", caplog)

            # B tries to read A's invoice + image.
            r_doc = test_client.get(f"/api/invoices/{invoice_id_a}")
            assert r_doc.status_code == 404
            r_img = test_client.get(f"/api/invoices/{invoice_id_a}/image")
            assert r_img.status_code == 404
        finally:
            pl.PipelineRunner.run = original  # type: ignore[assignment]
            er._pipeline_singleton = None
