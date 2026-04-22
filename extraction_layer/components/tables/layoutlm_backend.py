"""
LayoutLMv3 table extractor — SCAFFOLDED, not implemented.

This backend ties to the G3 escalation path (`research.md` §9.6) — if we
ever fine-tune LayoutLMv3 for header extraction, the same model can be
reused for item tokens by extending the IOB2 label set with per-column
tags. Only relevant after that investment is made.

To enable:
  1. Do the LayoutLMv3 fine-tune work in Component G3 first, or in parallel.
  2. Extend the IOB2 label set with B-ITEM_DESC / I-ITEM_DESC,
     B-ITEM_QTY / I-ITEM_QTY, B-ITEM_NET_PRICE / ..., etc. Train on the
     katanaml Donut ground truth converted to token labels.
  3. Export to ONNX, convert to OpenVINO IR at FP32 for CPU parity.
  4. Implement ``.extract()`` to run the fine-tuned model and assemble
     items from B/I token sequences.
  5. Remove this notice.
"""

from typing import Any

from extraction_layer.components.ocr.types import OCRResult

from .base import BaseTableExtractor
from .types import TableExtractionResult


class LayoutLMTableExtractor(BaseTableExtractor):
    """Scaffold for a LayoutLMv3-backed table extractor. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    @property
    def extractor_name(self) -> str:
        return "layoutlm"

    def extract(self, ocr_result: OCRResult) -> TableExtractionResult:
        raise NotImplementedError(
            "LayoutLMTableExtractor is scaffolded but not implemented at PoC time. "
            "See components/tables/layoutlm_backend.py for enablement steps."
        )
