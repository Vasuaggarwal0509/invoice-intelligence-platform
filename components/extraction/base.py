"""
Extraction component — abstract backend interface.

An extractor takes an OCRResult (from `components.ocr`) and produces an
ExtractionResult with per-field values + confidence + provenance.

Adding a new extractor:
    1. Create `components/extraction/<backend>/extractor.py` (or a module
       at package level if it's single-file).
    2. Subclass `BaseExtractor`. Implement `extractor_name` and
       `extract(ocr_result)`.
    3. Register the dotted class path in `components/extraction/factory.py`.
    4. Add tests under `components/extraction/tests/`.
"""

from abc import ABC, abstractmethod

from components.ocr.types import OCRResult

from .types import ExtractionResult


class BaseExtractor(ABC):
    """Abstract extractor backend.

    Upstream (OCR) emits `OCRResult`; downstream (validation, export) consumes
    `ExtractionResult`. Extractors are swappable via the factory; callers never
    branch on which extractor produced the result.
    """

    @property
    @abstractmethod
    def extractor_name(self) -> str:
        """Short identifier stored in ExtractionResult.extractor."""
        raise NotImplementedError

    @abstractmethod
    def extract(self, ocr_result: OCRResult) -> ExtractionResult:
        """Run extraction on one OCR'd invoice.

        Args:
            ocr_result: Output of the OCR stage.

        Returns:
            ExtractionResult with per-field values, confidence, provenance.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} extractor='{self.extractor_name}'>"
