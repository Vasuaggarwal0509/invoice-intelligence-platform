"""
PipelineRunner — orchestrates OCR -> extraction -> tables -> validation.

Singleton-ish: one instance at FastAPI app start-up, reused for every
request. The OCR model is loaded once (on `warmup()`) so the second
request onwards skips the model-load latency.

The runner does not cache — caching lives in `PipelineCache`. The
runner's job is purely to produce the pipeline output. Keeps
responsibilities separate so either piece can be swapped without
touching the other.
"""

from typing import Any

from components.extraction import ExtractionResult, make_extractor
from components.ocr import OCRResult, make_ocr
from components.tables import TableExtractionResult, make_table_extractor
from components.validation import ValidationEngine, ValidationResult


class PipelineRunner:
    """Runs OCR + extraction + tables + validation for one image."""

    def __init__(
        self,
        *,
        ocr_backend: str = "rapidocr",
        extractor_backend: str = "heuristic",
        table_backend: str = "spatial",
    ) -> None:
        self._ocr = make_ocr(ocr_backend)
        self._extractor = make_extractor(extractor_backend)
        self._tables = make_table_extractor(table_backend)
        self._validation = ValidationEngine()
        self._warmed = False

    def warmup(self) -> None:
        if not self._warmed:
            self._ocr.warmup()
            self._warmed = True

    def run(
        self,
        image: Any,
        *,
        validate: bool = True,
    ) -> tuple[OCRResult, ExtractionResult, TableExtractionResult, ValidationResult | None]:
        """Full pipeline on a single image. Returns the four stage outputs."""
        ocr_result = self._ocr.ocr(image)
        extraction = self._extractor.extract(ocr_result)
        tables = self._tables.extract(ocr_result)
        validation = None
        if validate:
            validation = self._validation.validate(extraction, tables)
        return ocr_result, extraction, tables, validation
