"""
LayoutLMv3 extractor — SCAFFOLDED, not implemented (G3 fallback path).

This backend is the concrete escalation path from `research.md` §9 when
heuristic G1+G2 falls short of the 0.90 average-per-field F1 gate. See
`progress.md` entry for 2026-04-18 for the sign-off notes on why this
is *not* our first path.

To enable:

  1. Donut-JSON → IOB2 token-label conversion for the katanaml train split
     (~1-3 days of custom engineering — no standard pipeline exists).
  2. Fine-tune `microsoft/layoutlmv3-base` with a
     `LayoutLMv3ForTokenClassification` head on our token labels
     (~2-4 days; needs Colab GPU).
  3. Export the fine-tuned model to ONNX.
  4. Convert ONNX → OpenVINO IR at **FP32 only** (preserves parity
     bit-for-bit per OpenVINO docs; no quantisation for now).
  5. Benchmark CPU latency on target Windows hardware — ship only if the
     inference path beats G1+G2 on F1 **and** stays under 1.5 s / invoice.
  6. Replace the NotImplementedError raise with a real implementation that
     returns an ExtractionResult matching our shared schema.
  7. Remove this notice.
"""

from typing import Any

from extraction_layer.components.ocr.types import OCRResult

from .base import BaseExtractor
from .types import ExtractionResult


class LayoutLMv3Extractor(BaseExtractor):
    """Scaffold for the LayoutLMv3 + OpenVINO extractor. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        # Accept kwargs for forward compatibility. No heavy imports — ONNX /
        # OpenVINO are lazy-loaded once this backend is implemented.
        pass

    @property
    def extractor_name(self) -> str:
        return "layoutlmv3"

    def extract(self, ocr_result: OCRResult) -> ExtractionResult:
        raise NotImplementedError(
            "LayoutLMv3Extractor is scaffolded but not implemented at PoC time. "
            "Triggered only if G1+G2 fail the 0.90 F1 gate. See "
            "components/extraction/layoutlm_backend.py for enablement steps."
        )
