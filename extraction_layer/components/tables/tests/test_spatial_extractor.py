"""End-to-end tests for SpatialTableExtractor."""

import pytest

from extraction_layer.components.tables import make_table_extractor
from extraction_layer.components.tables.types import TableExtractionResult

from ._fixtures import (
    no_items_anchor,
    no_summary_anchor,
    one_item_with_3line_description,
    three_items_single_line,
)


@pytest.fixture
def extractor():
    return make_table_extractor("spatial")


class TestOneItem3LineDescription:
    @pytest.fixture
    def result(self, extractor) -> TableExtractionResult:
        return extractor.extract(one_item_with_3line_description())

    def test_returns_result_with_one_item(self, result):
        assert isinstance(result, TableExtractionResult)
        assert result.extractor == "spatial"
        assert result.duration_ms >= 0
        assert len(result.items) == 1

    def test_decimals_assigned_left_to_right(self, result):
        item = result.items[0]
        assert item.item_qty == "2,00"
        assert item.item_net_price == "444,60"
        assert item.item_net_worth == "889,20"
        assert item.item_gross_worth == "978,12"

    def test_vat_extracted(self, result):
        assert result.items[0].item_vat == "10%"

    def test_description_combines_all_three_lines(self, result):
        desc = result.items[0].item_desc
        assert desc is not None
        assert "Marble Lapis Inlay Chess" in desc
        assert "Table Top With 2 Pieces" in desc
        assert "Wooden Stand W537" in desc

    def test_description_does_not_include_numeric_columns(self, result):
        desc = result.items[0].item_desc
        assert "444,60" not in desc
        assert "10%" not in desc
        assert "each" not in desc

    def test_diagnostics_include_anchor_count(self, result):
        assert result.diagnostics["anchor_count"] == 1


class TestThreeItemsSingleLine:
    @pytest.fixture
    def result(self, extractor) -> TableExtractionResult:
        return extractor.extract(three_items_single_line())

    def test_three_items_detected(self, result):
        assert len(result.items) == 3

    def test_item_1_fields(self, result):
        item = result.items[0]
        assert item.item_desc == "Nintendo Gameboy"
        assert item.item_qty == "1,00"
        assert item.item_net_price == "65,00"
        assert item.item_net_worth == "65,00"
        assert item.item_vat == "10%"
        assert item.item_gross_worth == "71,50"

    def test_item_2_fields(self, result):
        item = result.items[1]
        assert item.item_desc == "Sony Playstation 4"
        assert item.item_qty == "3,00"
        assert item.item_net_price == "399,99"
        assert item.item_net_worth == "1199,97"
        assert item.item_gross_worth == "1319,97"

    def test_item_3_fields(self, result):
        item = result.items[2]
        assert item.item_desc == "Atari Flashback"
        assert item.item_qty == "4,00"
        assert item.item_net_price == "8,50"
        assert item.item_net_worth == "34,00"
        assert item.item_gross_worth == "37,40"


class TestEdgeCases:
    def test_no_items_anchor_returns_empty(self, extractor):
        result = extractor.extract(no_items_anchor())
        assert result.items == []
        assert "no ITEMS anchor" in str(result.diagnostics.get("reason", ""))

    def test_no_summary_anchor_still_extracts_items(self, extractor):
        result = extractor.extract(no_summary_anchor())
        assert len(result.items) == 1
        assert result.items[0].item_qty == "2,00"
        # summary_top_y is None in diagnostics, but the extractor falls back to page bottom
        assert result.diagnostics["summary_top_y"] is None
