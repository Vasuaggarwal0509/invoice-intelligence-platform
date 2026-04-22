"""Tests for the OCR output schema (Pydantic models)."""

import pytest
from pydantic import ValidationError

from components.ocr.types import BoundingBox, Line, OCRResult, PageSize, Token


class TestBoundingBox:
    def test_valid_bbox(self):
        bbox = BoundingBox(x0=0, y0=0, x1=10, y1=5)
        assert bbox.width == 10
        assert bbox.height == 5
        assert bbox.as_tuple() == (0, 0, 10, 5)

    def test_x1_must_be_ge_x0(self):
        with pytest.raises(ValidationError):
            BoundingBox(x0=10, y0=0, x1=5, y1=5)

    def test_y1_must_be_ge_y0(self):
        with pytest.raises(ValidationError):
            BoundingBox(x0=0, y0=10, x1=10, y1=5)

    def test_frozen(self):
        bbox = BoundingBox(x0=0, y0=0, x1=10, y1=5)
        with pytest.raises((ValidationError, TypeError)):
            bbox.x0 = 5  # frozen model; mutation must fail

    def test_zero_extent_is_allowed(self):
        # A degenerate bbox is legal (some OCR engines emit zero-width hits);
        # consumers decide whether to filter.
        bbox = BoundingBox(x0=5, y0=5, x1=5, y1=5)
        assert bbox.width == 0
        assert bbox.height == 0


class TestToken:
    def _bbox(self) -> BoundingBox:
        return BoundingBox(x0=0, y0=0, x1=70, y1=20)

    def test_valid_token(self):
        token = Token(text="INVOICE", bbox=self._bbox(), confidence=0.95)
        assert token.text == "INVOICE"
        assert token.confidence == 0.95
        assert token.polygon is None

    def test_confidence_in_range(self):
        bbox = self._bbox()
        with pytest.raises(ValidationError):
            Token(text="x", bbox=bbox, confidence=1.5)
        with pytest.raises(ValidationError):
            Token(text="x", bbox=bbox, confidence=-0.1)

    def test_text_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            Token(text="", bbox=self._bbox(), confidence=0.9)

    def test_polygon_accepted(self):
        polygon = [[0.0, 0.0], [70.0, 0.0], [70.0, 20.0], [0.0, 20.0]]
        token = Token(
            text="INVOICE",
            bbox=self._bbox(),
            polygon=polygon,
            confidence=0.9,
        )
        assert token.polygon == polygon


class TestLine:
    def test_line_with_tokens(self):
        bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
        token_bbox = BoundingBox(x0=0, y0=0, x1=40, y1=20)
        line = Line(
            text="INVOICE 12345",
            bbox=bbox,
            tokens=[Token(text="INVOICE", bbox=token_bbox, confidence=0.9)],
            confidence=0.9,
        )
        assert len(line.tokens) == 1
        assert line.tokens[0].text == "INVOICE"

    def test_line_tokens_default_empty(self):
        bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
        line = Line(text="just text", bbox=bbox, confidence=0.8)
        assert line.tokens == []


class TestPageSize:
    def test_valid_size(self):
        page = PageSize(width=800, height=600)
        assert page.width == 800
        assert page.height == 600

    def test_dimensions_must_be_positive(self):
        with pytest.raises(ValidationError):
            PageSize(width=0, height=600)
        with pytest.raises(ValidationError):
            PageSize(width=800, height=-1)


class TestOCRResult:
    def test_minimal_result(self):
        result = OCRResult(
            tokens=[],
            lines=[],
            page=PageSize(width=800, height=600),
            backend="rapidocr",
            duration_ms=42.0,
        )
        assert result.backend == "rapidocr"
        assert result.page.width == 800
        assert result.tokens == []
        assert result.lines == []

    def test_backend_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            OCRResult(
                tokens=[],
                lines=[],
                page=PageSize(width=10, height=10),
                backend="",
                duration_ms=0.0,
            )

    def test_duration_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            OCRResult(
                tokens=[],
                lines=[],
                page=PageSize(width=10, height=10),
                backend="rapidocr",
                duration_ms=-0.001,
            )

    def test_json_roundtrip(self):
        bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
        token = Token(text="INVOICE", bbox=bbox, confidence=0.9)
        line = Line(
            text="INVOICE 12345",
            bbox=bbox,
            polygon=[[0, 0], [100, 0], [100, 20], [0, 20]],
            tokens=[token],
            confidence=0.9,
        )
        result = OCRResult(
            tokens=[token],
            lines=[line],
            page=PageSize(width=800, height=600),
            backend="rapidocr",
            duration_ms=42.0,
        )
        dumped = result.model_dump_json()
        roundtrip = OCRResult.model_validate_json(dumped)
        assert roundtrip.lines[0].text == "INVOICE 12345"
        assert roundtrip.lines[0].tokens[0].text == "INVOICE"
        assert roundtrip.tokens[0].confidence == 0.9
