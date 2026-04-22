"""
MIDD dataset loader — SCAFFOLDED, not implemented.

Target dataset for the post-PoC Indian specialisation phase (see
`research.md` §4.3 and `project.md` §6.3):

    Multi-Layout Invoice Document Dataset (MIDD)
    * 630 real Indian GST invoices, 4 layouts
    * CC-BY 4.0
    * IOB-annotated NER labels including GSTIN, CGST/SGST/IGST fields
    * Zenodo DOI: 10.5281/zenodo.5113009  (1.1 MB RAR of IOB files)
    * Paper: MDPI Data 6(7):78 (2021), Baviskar et al., Symbiosis Pune

To enable:
  1. Download the RAR from Zenodo and extract under ``data/midd/``.
  2. Implement ``load() / get() / count()`` to read the IOB files and the
     matching invoice images, emitting :class:`Sample` instances. The
     ``ground_truth`` dict should preserve the IOB label sequence plus a
     normalised field view (GSTIN, CGST, SGST, IGST, HSN, ...).
  3. Confirm the split convention (the MIDD paper does not pre-split;
     we will define a held-out split with a versioned seed).
  4. Remove this notice.
"""

from typing import Any, Iterator

from ..base import BaseDataset
from ..types import Sample


class MIDDDataset(BaseDataset):
    """Scaffold for the MIDD Indian-invoice dataset. Not yet implemented."""

    _NAME = "midd"

    def __init__(self, **_kwargs: Any) -> None:
        # Accept arbitrary kwargs for forward compatibility. No heavy imports,
        # no filesystem work — the real implementation will add both.
        pass

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def splits(self) -> list[str]:
        # Placeholder; real implementation will define a reproducible split.
        return ["train", "test"]

    def load(self, split: str) -> Iterator[Sample]:
        raise NotImplementedError(
            "MIDDDataset is scaffolded but not implemented at PoC time. "
            "See data_sources/midd/loader.py for enablement steps."
        )

    def get(self, split: str, index: int) -> Sample:
        raise NotImplementedError(
            "MIDDDataset is scaffolded but not implemented at PoC time."
        )

    def count(self, split: str) -> int:
        raise NotImplementedError(
            "MIDDDataset is scaffolded but not implemented at PoC time."
        )
