"""
PP-StructureV3 table extractor — SCAFFOLDED, not implemented.

Reason held: PaddleOCR's PP-StructureV3 runs at ~3.7 s / page on Intel CPU
(per `research.md` §10.3), which stacked on our ~5.7 s RapidOCR pushes
end-to-end latency near 10 s per invoice. For the single-template
katanaml PoC, the custom spatial extractor is enough; PP-Structure becomes
relevant when we have multi-template data (MIDD phase) or when structure
recognition becomes the limiting factor.

To enable:
  1. ``uv pip install -e ".[paddleocr]"`` (drags in the full PaddlePaddle
     runtime — expect the same install friction documented in the OCR
     scaffolded-backend file).
  2. Implement ``.extract()`` using ``paddleocr.PPStructure(...)`` restricted
     to the table module, map the output to `TableExtractionResult`.
  3. Remove this notice.
"""

from typing import Any

from extraction_layer.components.ocr.types import OCRResult

from .base import BaseTableExtractor
from .types import TableExtractionResult


class PPStructureTableExtractor(BaseTableExtractor):
    """Scaffold for the PP-StructureV3 table backend. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    @property
    def extractor_name(self) -> str:
        return "pp_structure"

    def extract(self, ocr_result: OCRResult) -> TableExtractionResult:
        raise NotImplementedError(
            "PPStructureTableExtractor is scaffolded but not implemented at PoC time. "
            "See components/tables/pp_structure_backend.py for enablement steps."
        )
