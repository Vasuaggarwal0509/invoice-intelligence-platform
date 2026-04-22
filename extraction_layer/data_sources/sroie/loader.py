"""
SROIE dataset loader — SCAFFOLDED, not implemented.

Reference benchmark for external calibration (`research.md` §4.4):

    ICDAR 2019 SROIE — Scanned Receipts OCR and Information Extraction
    * 1000 scanned receipts (Singapore origin)
    * Labeled: company, date, address, total
    * Widely cited in document-AI literature; useful for cross-checking our
      per-field F1 numbers against published results.

To enable:
  1. Obtain the SROIE competition data via Kaggle or the official ICDAR
     mirror. Cache under ``data/sroie/``.
  2. Implement ``load() / get() / count()`` to emit :class:`Sample` instances;
     store the four labeled fields under ``ground_truth``.
  3. Remove this notice.

This scaffold exists so ``make_dataset('sroie')`` is discoverable on day one.
"""

from typing import Any, Iterator

from ..base import BaseDataset
from ..types import Sample


class SROIEDataset(BaseDataset):
    """Scaffold for the SROIE reference dataset. Not yet implemented."""

    _NAME = "sroie"

    def __init__(self, **_kwargs: Any) -> None:
        pass

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def splits(self) -> list[str]:
        return ["train", "test"]

    def load(self, split: str) -> Iterator[Sample]:
        raise NotImplementedError(
            "SROIEDataset is scaffolded but not implemented at PoC time. "
            "See data_sources/sroie/loader.py for enablement steps."
        )

    def get(self, split: str, index: int) -> Sample:
        raise NotImplementedError(
            "SROIEDataset is scaffolded but not implemented at PoC time."
        )

    def count(self, split: str) -> int:
        raise NotImplementedError(
            "SROIEDataset is scaffolded but not implemented at PoC time."
        )
