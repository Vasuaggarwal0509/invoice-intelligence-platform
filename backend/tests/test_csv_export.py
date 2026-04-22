"""Tests for the CSV exporter (Component M)."""

import csv
import io

from backend.app.csv_export import (
    ALL_COLUMNS,
    batch_to_csv,
    invoice_to_csv,
    invoice_to_csv_rows,
)
from components.extraction.types import ExtractedField, ExtractionResult
from components.tables.types import InvoiceItem, TableExtractionResult


def _extraction(**overrides: str) -> ExtractionResult:
    fields = {
        "invoice_no": "97159829",
        "invoice_date": "09/18/2015",
        "seller": "Bradley-Andrade 9879 Elizabeth Common",
        "client": "Castro PLC Unit 9678 Box 9664",
        "seller_tax_id": "985-73-8194",
        "client_tax_id": "994-72-1270",
        "iban": "GB82WEST12345698765432",
    }
    fields.update(overrides)
    return ExtractionResult(
        fields={
            name: ExtractedField(
                name=name,
                value=value,
                confidence=0.9,
                source="regex",
            )
            for name, value in fields.items()
        },
        extractor="heuristic",
        duration_ms=0.0,
    )


def _tables(items: list[InvoiceItem] | None = None) -> TableExtractionResult:
    if items is None:
        items = [
            InvoiceItem(
                item_desc="Marble Chess Table",
                item_qty="2,00",
                item_net_price="444,60",
                item_net_worth="889,20",
                item_vat="10%",
                item_gross_worth="978,12",
            )
        ]
    return TableExtractionResult(items=items, extractor="spatial", duration_ms=0.0)


class TestInvoiceToCsvRows:
    def test_one_item(self):
        rows = invoice_to_csv_rows(_extraction(), _tables())
        assert len(rows) == 1
        row = rows[0]
        assert row["invoice_no"] == "97159829"
        assert row["item_desc"] == "Marble Chess Table"
        assert row["item_qty"] == "2,00"
        assert row["item_index"] == "0"

    def test_header_fields_present_on_every_row(self):
        items = [
            InvoiceItem(item_desc=f"desc-{i}", item_qty=f"{i},00")
            for i in range(3)
        ]
        rows = invoice_to_csv_rows(_extraction(), _tables(items))
        assert len(rows) == 3
        for i, row in enumerate(rows):
            assert row["invoice_no"] == "97159829"
            assert row["item_index"] == str(i)
            assert row["item_desc"] == f"desc-{i}"

    def test_no_items_emits_single_row_with_blank_items(self):
        rows = invoice_to_csv_rows(_extraction(), _tables(items=[]))
        assert len(rows) == 1
        row = rows[0]
        assert row["invoice_no"] == "97159829"
        assert row["item_desc"] == ""
        assert row["item_qty"] == ""

    def test_missing_header_fields_become_empty_strings(self):
        extraction = ExtractionResult(
            fields={},
            extractor="heuristic",
            duration_ms=0.0,
        )
        rows = invoice_to_csv_rows(extraction, _tables())
        assert rows[0]["invoice_no"] == ""
        assert rows[0]["seller"] == ""
        assert rows[0]["iban"] == ""

    def test_none_tables_is_handled(self):
        rows = invoice_to_csv_rows(_extraction(), tables=None)
        assert len(rows) == 1
        assert rows[0]["item_desc"] == ""


class TestInvoiceToCsv:
    def test_returns_header_and_rows(self):
        text = invoice_to_csv(_extraction(), _tables())
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames == ALL_COLUMNS
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["invoice_no"] == "97159829"

    def test_commas_in_values_are_quoted(self):
        extraction = _extraction(seller="Acme, Inc. 123 Main Street")
        text = invoice_to_csv(extraction, _tables())
        # The seller cell contains a comma — quoting must keep it intact.
        reader = csv.DictReader(io.StringIO(text))
        row = next(reader)
        assert row["seller"] == "Acme, Inc. 123 Main Street"

    def test_has_trailing_newline(self):
        text = invoice_to_csv(_extraction(), _tables())
        assert text.endswith("\r\n") or text.endswith("\n")


class TestBatchToCsv:
    def test_batch_concatenates_rows(self):
        a = _extraction(invoice_no="1")
        b = _extraction(invoice_no="2")
        text = batch_to_csv([a, b], [_tables(), _tables()])
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == 2
        assert {r["invoice_no"] for r in rows} == {"1", "2"}

    def test_batch_length_mismatch_raises(self):
        import pytest

        with pytest.raises(ValueError):
            batch_to_csv([_extraction()], [_tables(), _tables()])

    def test_batch_defaults_tables_to_none(self):
        # When tables_list is not passed, every extraction gets a blank item row.
        text = batch_to_csv([_extraction(), _extraction()])
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == 2
        assert all(r["item_desc"] == "" for r in rows)
