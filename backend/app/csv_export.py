"""
Component M — CSV export.

Turns an `ExtractionResult` + `TableExtractionResult` into a CSV file
with one row per line item. Header fields (invoice_no, dates, parties,
tax ids, IBAN) are repeated on every row — this is the "flat" format
most spreadsheets / accounting-software importers accept.

If you want a stricter Tally voucher format later, keep this generic
exporter and add a second adapter (e.g. `to_tally_csv`) that re-maps
column names. The generic format is the right default for a PoC.
"""

import csv
import io
from typing import Any

from components.extraction.types import ExtractionResult
from components.tables.types import InvoiceItem, TableExtractionResult


HEADER_COLUMNS: list[str] = [
    "invoice_no",
    "invoice_date",
    "seller",
    "client",
    "seller_tax_id",
    "client_tax_id",
    "iban",
]

ITEM_COLUMNS: list[str] = [
    "item_index",
    "item_desc",
    "item_qty",
    "item_net_price",
    "item_net_worth",
    "item_vat",
    "item_gross_worth",
]

ALL_COLUMNS: list[str] = HEADER_COLUMNS + ITEM_COLUMNS


def _header_row(extraction: ExtractionResult) -> dict[str, str]:
    """Pull the header field values out of an ExtractionResult into a dict."""
    row: dict[str, str] = {}
    for name in HEADER_COLUMNS:
        value = extraction.get_value(name)
        row[name] = value if value is not None else ""
    return row


def _item_row(item: InvoiceItem, index: int) -> dict[str, str]:
    data = item.as_dict()
    row: dict[str, str] = {"item_index": str(index)}
    for col in ITEM_COLUMNS:
        if col == "item_index":
            continue
        value = data.get(col)
        row[col] = value if value is not None else ""
    return row


def invoice_to_csv_rows(
    extraction: ExtractionResult,
    tables: TableExtractionResult | None = None,
) -> list[dict[str, str]]:
    """Produce CSV row dicts for one invoice.

    If `tables` has items, emit one row per item (header fields repeated).
    If `tables` is None or has no items, emit a single row with item
    columns blank — the invoice still exports cleanly.
    """
    header = _header_row(extraction)
    items = tables.items if tables is not None else []
    if not items:
        blank_item: dict[str, str] = {col: "" for col in ITEM_COLUMNS}
        return [{**header, **blank_item}]
    return [{**header, **_item_row(item, i)} for i, item in enumerate(items)]


def write_csv(
    rows: list[dict[str, Any]],
    *,
    columns: list[str] | None = None,
) -> str:
    """Serialise a list of row-dicts to a CSV string."""
    if columns is None:
        columns = ALL_COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return buf.getvalue()


def invoice_to_csv(
    extraction: ExtractionResult,
    tables: TableExtractionResult | None = None,
) -> str:
    """One-shot: invoice -> CSV text."""
    return write_csv(invoice_to_csv_rows(extraction, tables))


def batch_to_csv(
    extractions: list[ExtractionResult],
    tables_list: list[TableExtractionResult | None] | None = None,
) -> str:
    """Aggregate a batch: one big CSV with rows from all invoices."""
    if tables_list is None:
        tables_list = [None] * len(extractions)
    if len(tables_list) != len(extractions):
        raise ValueError(
            f"tables_list length ({len(tables_list)}) must match "
            f"extractions length ({len(extractions)})"
        )
    all_rows: list[dict[str, Any]] = []
    for extraction, tables in zip(extractions, tables_list):
        all_rows.extend(invoice_to_csv_rows(extraction, tables))
    return write_csv(all_rows)
