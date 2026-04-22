"""Tests for InvoiceItem and TableExtractionResult."""

import pytest
from pydantic import ValidationError

from extraction_layer.components.tables.types import InvoiceItem, TableExtractionResult


class TestInvoiceItem:
    def test_all_fields_default_none(self):
        item = InvoiceItem()
        assert item.item_desc is None
        assert item.item_qty is None
        assert item.item_net_price is None
        assert item.item_net_worth is None
        assert item.item_vat is None
        assert item.item_gross_worth is None

    def test_populated_item(self):
        item = InvoiceItem(
            item_desc="Widget",
            item_qty="1,00",
            item_net_price="10,00",
            item_net_worth="10,00",
            item_vat="10%",
            item_gross_worth="11,00",
        )
        assert item.item_desc == "Widget"
        assert item.item_qty == "1,00"

    def test_frozen(self):
        item = InvoiceItem(item_desc="x")
        with pytest.raises((ValidationError, TypeError)):
            item.item_desc = "y"

    def test_as_dict(self):
        item = InvoiceItem(item_desc="Widget", item_qty="1,00")
        d = item.as_dict()
        assert d == {
            "item_desc": "Widget",
            "item_qty": "1,00",
            "item_net_price": None,
            "item_net_worth": None,
            "item_vat": None,
            "item_gross_worth": None,
        }


class TestTableExtractionResult:
    def test_minimal_empty_items(self):
        r = TableExtractionResult(items=[], extractor="spatial", duration_ms=0.0)
        assert r.items == []
        assert r.extractor == "spatial"

    def test_extractor_non_empty(self):
        with pytest.raises(ValidationError):
            TableExtractionResult(items=[], extractor="", duration_ms=0.0)

    def test_duration_non_negative(self):
        with pytest.raises(ValidationError):
            TableExtractionResult(items=[], extractor="x", duration_ms=-1.0)

    def test_json_roundtrip(self):
        r = TableExtractionResult(
            items=[InvoiceItem(item_desc="Widget", item_qty="2,00")],
            extractor="spatial",
            duration_ms=5.5,
            diagnostics={"anchor_count": 1},
        )
        dumped = r.model_dump_json()
        roundtrip = TableExtractionResult.model_validate_json(dumped)
        assert roundtrip.items[0].item_desc == "Widget"
        assert roundtrip.diagnostics["anchor_count"] == 1
