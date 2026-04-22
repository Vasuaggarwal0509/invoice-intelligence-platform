"""Table-extraction component — pipeline stage 7: OCRResult -> TableExtractionResult.

Public surface:

    from extraction_layer.components.tables import make_table_extractor
    table_extractor = make_table_extractor("spatial")
    table_result = table_extractor.extract(ocr_result)
    for item in table_result.items:
        print(item.item_desc, item.item_qty, item.item_gross_worth)

Downstream stages (validation, CSV export, UI) consume `TableExtractionResult`
and never branch on the concrete backend.
"""

from .base import BaseTableExtractor
from .factory import available_table_extractors, make_table_extractor
from .types import InvoiceItem, TableExtractionResult

__all__ = [
    "BaseTableExtractor",
    "InvoiceItem",
    "TableExtractionResult",
    "available_table_extractors",
    "make_table_extractor",
]
