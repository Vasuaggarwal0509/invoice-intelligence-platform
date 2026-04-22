"""Extraction component — pipeline stage 6: OCRResult -> ExtractionResult.

Public surface:

    from components.extraction import make_extractor
    extractor = make_extractor("heuristic")
    result = extractor.extract(ocr_result)
    result.get_value("invoice_no")

Downstream stages (validation, CSV export, UI) consume ExtractionResult and
never branch on the concrete backend. See README.md for details.
"""

from .base import BaseExtractor
from .factory import available_extractors, make_extractor
from .types import ExtractedField, ExtractionResult

__all__ = [
    "BaseExtractor",
    "ExtractedField",
    "ExtractionResult",
    "available_extractors",
    "make_extractor",
]
