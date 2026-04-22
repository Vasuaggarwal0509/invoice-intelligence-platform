"""Hand-crafted ExtractionResult and TableExtractionResult builders for tests.

Kept out of the live schema because production code doesn't construct
these by hand — they come from the extraction / tables components.
"""

from extraction_layer.components.extraction.types import ExtractedField, ExtractionResult
from extraction_layer.components.tables.types import InvoiceItem, TableExtractionResult


def _field(name: str, value: str | None, confidence: float = 0.95) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=value,
        confidence=confidence if value is not None else 0.0,
        source="regex" if value is not None else "none",
    )


def make_extraction(
    *,
    invoice_no: str | None = "97159829",
    invoice_date: str | None = "09/18/2015",
    seller_tax_id: str | None = "985-73-8194",
    client_tax_id: str | None = "994-72-1270",
    iban: str | None = "GB82WEST12345698765432",  # ECBS test IBAN
    seller: str | None = "Bradley-Andrade 9879 Elizabeth Common Lake Jonathan, RI 12335",
    client: str | None = "Castro PLC Unit 9678 Box 9664 DPO AP 69387",
) -> ExtractionResult:
    return ExtractionResult(
        fields={
            "invoice_no": _field("invoice_no", invoice_no),
            "invoice_date": _field("invoice_date", invoice_date),
            "seller_tax_id": _field("seller_tax_id", seller_tax_id),
            "client_tax_id": _field("client_tax_id", client_tax_id),
            "iban": _field("iban", iban),
            "seller": _field("seller", seller),
            "client": _field("client", client),
        },
        extractor="heuristic",
        duration_ms=0.0,
    )


def make_item(
    *,
    qty: str | None = "2,00",
    net_price: str | None = "10,00",
    net_worth: str | None = "20,00",
    vat: str | None = "10%",
    gross_worth: str | None = "22,00",
    desc: str | None = "Widget",
) -> InvoiceItem:
    return InvoiceItem(
        item_desc=desc,
        item_qty=qty,
        item_net_price=net_price,
        item_net_worth=net_worth,
        item_vat=vat,
        item_gross_worth=gross_worth,
    )


def make_tables(items: list[InvoiceItem] | None = None) -> TableExtractionResult:
    if items is None:
        items = [make_item()]
    return TableExtractionResult(
        items=items,
        extractor="spatial",
        duration_ms=0.0,
    )
