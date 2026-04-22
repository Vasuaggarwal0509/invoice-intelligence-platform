"""Tests for the InvoiceInput wire contract + BaseOCR.ocr_invoice default impl."""

import pytest
from pydantic import ValidationError

from extraction_layer.components.ocr import InvoiceInput
from extraction_layer.components.ocr.base import BaseOCR
from extraction_layer.components.ocr.types import OCRResult, PageSize


# ----- stub backend for testing ocr_invoice delegation -----------------------


class _StubOCR(BaseOCR):
    """Stub that records what was passed to .ocr() so we can assert delegation."""

    def __init__(self) -> None:
        self.last_input = None

    @property
    def backend_name(self) -> str:
        return "stub"

    def ocr(self, image):
        self.last_input = image
        return OCRResult(
            tokens=[],
            lines=[],
            page=PageSize(width=1, height=1),
            backend="stub",
            duration_ms=0.0,
        )


# ----- InvoiceInput validation ----------------------------------------------


class TestInvoiceInputValidation:
    def test_accepts_bytes(self):
        inp = InvoiceInput(id="x", content_type="image/png", image_bytes=b"\x89PNG...")
        assert inp.image_bytes == b"\x89PNG..."
        assert inp.image_uri is None

    def test_accepts_uri(self):
        inp = InvoiceInput(
            id="x",
            content_type="application/pdf",
            image_uri="s3://bucket/invoice-001.pdf",
        )
        assert inp.image_uri == "s3://bucket/invoice-001.pdf"
        assert inp.image_bytes is None

    def test_rejects_both_bytes_and_uri(self):
        with pytest.raises(ValidationError):
            InvoiceInput(
                id="x",
                content_type="image/png",
                image_bytes=b"x",
                image_uri="https://example.com/x.png",
            )

    def test_rejects_neither_bytes_nor_uri(self):
        with pytest.raises(ValidationError):
            InvoiceInput(id="x", content_type="image/png")

    def test_rejects_empty_bytes(self):
        # "provided but empty" is the same as "not provided" for our purposes.
        with pytest.raises(ValidationError):
            InvoiceInput(id="x", content_type="image/png", image_bytes=b"")

    def test_rejects_empty_uri(self):
        with pytest.raises(ValidationError):
            InvoiceInput(id="x", content_type="image/png", image_uri="   ")

    def test_id_required_non_empty(self):
        with pytest.raises(ValidationError):
            InvoiceInput(id="", content_type="image/png", image_bytes=b"x")

    def test_rejects_unsupported_content_type(self):
        with pytest.raises(ValidationError):
            InvoiceInput(
                id="x",
                content_type="text/csv",
                image_bytes=b"x",
            )

    def test_metadata_defaults_empty(self):
        inp = InvoiceInput(id="x", content_type="image/png", image_bytes=b"x")
        assert inp.metadata == {}

    def test_metadata_preserves_extras(self):
        inp = InvoiceInput(
            id="x",
            content_type="image/png",
            image_bytes=b"x",
            metadata={"source": "email", "sender": "foo@bar.com"},
        )
        assert inp.metadata["source"] == "email"

    def test_frozen(self):
        inp = InvoiceInput(id="x", content_type="image/png", image_bytes=b"x")
        with pytest.raises((ValidationError, TypeError)):
            inp.id = "y"


# ----- ocr_invoice delegation ------------------------------------------------


class TestOcrInvoiceDefaultImpl:
    def test_bytes_path_delegates_to_ocr(self):
        stub = _StubOCR()
        inp = InvoiceInput(id="x", content_type="image/png", image_bytes=b"\x89PNGfake")
        result = stub.ocr_invoice(inp)
        assert result.backend == "stub"
        assert stub.last_input == b"\x89PNGfake"

    def test_uri_path_raises_notimplemented(self):
        stub = _StubOCR()
        inp = InvoiceInput(
            id="x",
            content_type="application/pdf",
            image_uri="s3://bucket/a.pdf",
        )
        with pytest.raises(NotImplementedError) as exc_info:
            stub.ocr_invoice(inp)
        assert "image_uri" in str(exc_info.value)
        assert "_StubOCR" in str(exc_info.value)


# ----- JSON roundtrip (for schema / service boundary use) -------------------


class TestInvoiceInputJSON:
    def test_roundtrip_excludes_nothing_important(self):
        inp = InvoiceInput(
            id="x",
            content_type="image/png",
            image_bytes=b"\x89PNG",
            filename="invoice.png",
            metadata={"k": "v"},
        )
        dumped = inp.model_dump_json()
        roundtrip = InvoiceInput.model_validate_json(dumped)
        assert roundtrip.id == "x"
        assert roundtrip.content_type == "image/png"
        assert roundtrip.image_bytes == b"\x89PNG"
        assert roundtrip.filename == "invoice.png"
        assert roundtrip.metadata == {"k": "v"}

    def test_schema_generation_does_not_raise(self):
        # model_json_schema() is what tools/regen_schemas.py relies on.
        schema = InvoiceInput.model_json_schema()
        assert schema["title"] == "InvoiceInput"
        # `id` must be required
        assert "id" in schema.get("required", [])
        assert "content_type" in schema.get("required", [])
