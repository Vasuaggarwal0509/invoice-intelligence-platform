"""Tests for ExtractedField and ExtractionResult."""

import pytest
from pydantic import ValidationError

from extraction_layer.components.extraction.types import ExtractedField, ExtractionResult


class TestExtractedField:
    def test_valid_field(self):
        f = ExtractedField(
            name="invoice_no",
            value="12345",
            confidence=0.95,
            source="regex",
            source_detail="invoice_no anchor",
        )
        assert f.name == "invoice_no"
        assert f.value == "12345"
        assert f.confidence == 0.95

    def test_name_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            ExtractedField(name="", value="x", confidence=0.5)

    def test_confidence_in_range(self):
        with pytest.raises(ValidationError):
            ExtractedField(name="x", value="v", confidence=-0.01)
        with pytest.raises(ValidationError):
            ExtractedField(name="x", value="v", confidence=1.01)

    def test_missing_value_is_allowed(self):
        f = ExtractedField(name="invoice_no", value=None, confidence=0.0, source="none")
        assert f.value is None
        assert f.confidence == 0.0

    def test_frozen(self):
        f = ExtractedField(name="x", value="v", confidence=0.5)
        with pytest.raises((ValidationError, TypeError)):
            f.value = "y"


class TestExtractionResult:
    def _field(self, name, value, conf=0.9):
        return ExtractedField(name=name, value=value, confidence=conf, source="regex")

    def test_minimal_result(self):
        r = ExtractionResult(fields={}, extractor="heuristic", duration_ms=0.0)
        assert r.extractor == "heuristic"
        assert r.fields == {}

    def test_extractor_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            ExtractionResult(fields={}, extractor="", duration_ms=0.0)

    def test_duration_non_negative(self):
        with pytest.raises(ValidationError):
            ExtractionResult(fields={}, extractor="x", duration_ms=-0.001)

    def test_get_value(self):
        r = ExtractionResult(
            fields={
                "invoice_no": self._field("invoice_no", "12345"),
                "invoice_date": self._field("invoice_date", "01/02/2025"),
                "missing": ExtractedField(
                    name="missing", value=None, confidence=0.0, source="none"
                ),
            },
            extractor="heuristic",
            duration_ms=1.0,
        )
        assert r.get_value("invoice_no") == "12345"
        assert r.get_value("invoice_date") == "01/02/2025"
        assert r.get_value("missing") is None
        assert r.get_value("not_in_dict") is None

    def test_json_roundtrip(self):
        r = ExtractionResult(
            fields={"invoice_no": self._field("invoice_no", "12345", 0.95)},
            extractor="heuristic",
            duration_ms=42.0,
            diagnostics={"column_split_x": 400.0},
        )
        dumped = r.model_dump_json()
        roundtrip = ExtractionResult.model_validate_json(dumped)
        assert roundtrip.fields["invoice_no"].value == "12345"
        assert roundtrip.diagnostics["column_split_x"] == 400.0
