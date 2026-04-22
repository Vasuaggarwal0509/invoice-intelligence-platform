"""
Table-extraction component — abstract backend interface.

A table extractor takes an OCRResult (from `components.ocr`) and emits a
`TableExtractionResult` with the per-invoice `items` array.

Adding a new backend:
    1. Create a new subpackage or module under `components/tables/`.
    2. Subclass `BaseTableExtractor`. Implement `extractor_name` and
       `extract(ocr_result)`.
    3. Register the dotted class path in `components/tables/factory.py`.
    4. Add tests under `components/tables/tests/`.
"""

from abc import ABC, abstractmethod

from components.ocr.types import OCRResult

from .types import TableExtractionResult


class BaseTableExtractor(ABC):
    """Abstract table-extraction backend."""

    @property
    @abstractmethod
    def extractor_name(self) -> str:
        """Short identifier stored in TableExtractionResult.extractor."""
        raise NotImplementedError

    @abstractmethod
    def extract(self, ocr_result: OCRResult) -> TableExtractionResult:
        """Run table extraction on one OCR'd invoice."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} extractor='{self.extractor_name}'>"
