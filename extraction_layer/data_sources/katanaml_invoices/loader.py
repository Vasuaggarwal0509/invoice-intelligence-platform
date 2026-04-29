"""
Katanaml Invoices dataset loader.

Loads `katanaml-org/invoices-donut-data-v1` from the HuggingFace Hub and
exposes it as a `BaseDataset`. See `research.md` §4 for selection rationale:
501 real invoices, MIT licence, Donut-style JSON ground truth, pre-split.

The `ground_truth` on each `Sample` is a parsed dict of the form::

    {"gt_parse": {"header": {...}, "items": [...]}}

Use :meth:`header_of` / :meth:`items_of` to access without caring about the
Donut wrapping.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..base import BaseDataset
from ..types import Sample


class KatanamlInvoicesDataset(BaseDataset):
    """Primary PoC dataset — 501 real invoices with Donut-style ground truth."""

    DATASET_ID = "katanaml-org/invoices-donut-data-v1"
    _NAME = "katanaml-invoices-donut-v1"

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        hf_load_dataset_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the loader; downloads the dataset on first run.

        Args:
            cache_dir: Where to cache HuggingFace dataset files. Defaults to
                ``./data/katanaml/`` relative to the current working directory
                (the project's convention per `project.md` §8.0).
            hf_load_dataset_kwargs: Extra keyword arguments forwarded to
                ``datasets.load_dataset``.

        Raises:
            ImportError: If the HuggingFace ``datasets`` library is not installed.
        """
        try:
            from datasets import load_dataset as _hf_load_dataset  # type: ignore
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "The HuggingFace 'datasets' library is not installed. "
                "Install with: uv pip install 'datasets>=2.14'"
            ) from exc

        if cache_dir is None:
            # Default to <repo_root>/data/katanaml/ regardless of CWD.
            # __file__ = extraction_layer/data_sources/katanaml_invoices/loader.py
            # Kept at repo root (not nested under extraction_layer/) because
            # HuggingFace embeds the full absolute path into its lock filename,
            # and Windows' default MAX_PATH=260 is tight — any extra depth
            # overflows. See docs/progress.md restructure entry.
            _repo_root = Path(__file__).resolve().parent.parent.parent.parent
            cache_dir = _repo_root / "data" / "katanaml"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        extra = hf_load_dataset_kwargs or {}
        self._dataset = _hf_load_dataset(
            self.DATASET_ID,
            cache_dir=str(self._cache_dir),
            **extra,
        )

    # ----- BaseDataset interface -------------------------------------------

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def splits(self) -> list[str]:
        return list(self._dataset.keys())

    def load(self, split: str) -> Iterator[Sample]:
        self._require_split(split)
        total = len(self._dataset[split])
        for i in range(total):
            yield self.get(split, i)

    def get(self, split: str, index: int) -> Sample:
        self._require_split(split)
        subset = self._dataset[split]
        if index < 0 or index >= len(subset):
            raise IndexError(f"Index {index} out of range for split {split!r} (size {len(subset)})")
        row = subset[int(index)]
        return self._row_to_sample(row, split, int(index))

    def count(self, split: str) -> int:
        self._require_split(split)
        return len(self._dataset[split])

    # ----- Donut convenience accessors -------------------------------------

    @staticmethod
    def header_of(sample: Sample) -> dict[str, Any]:
        """Return ``ground_truth["gt_parse"]["header"]`` with fallbacks."""
        gt = sample.ground_truth
        inner = gt.get("gt_parse", gt) if isinstance(gt, dict) else {}
        header = inner.get("header", {}) if isinstance(inner, dict) else {}
        return header if isinstance(header, dict) else {}

    @staticmethod
    def items_of(sample: Sample) -> list[dict[str, Any]]:
        """Return ``ground_truth["gt_parse"]["items"]`` with fallbacks."""
        gt = sample.ground_truth
        inner = gt.get("gt_parse", gt) if isinstance(gt, dict) else {}
        items = inner.get("items", []) if isinstance(inner, dict) else []
        return items if isinstance(items, list) else []

    # ----- Helpers ---------------------------------------------------------

    def _require_split(self, split: str) -> None:
        if split not in self._dataset:
            raise ValueError(f"Unknown split {split!r}. Available: {self.splits}")

    def _row_to_sample(self, row: dict[str, Any], split: str, index: int) -> Sample:
        image = self._image_to_rgb_ndarray(row["image"])
        ground_truth = self._parse_ground_truth(row.get("ground_truth"))
        return Sample(
            id=f"katanaml-{split}-{index:05d}",
            image=image,
            ground_truth=ground_truth,
            split=split,
            source_dataset=self._NAME,
            metadata={
                "dataset_id": self.DATASET_ID,
                "row_index": index,
            },
        )

    @staticmethod
    def _image_to_rgb_ndarray(image: Any) -> np.ndarray:
        """Coerce HuggingFace's image column (PIL / ndarray) to HxWx3 uint8 RGB."""
        if isinstance(image, Image.Image):
            return np.array(image.convert("RGB"))
        if isinstance(image, np.ndarray):
            if image.ndim == 2:
                return np.stack([image] * 3, axis=-1).astype(np.uint8, copy=False)
            if image.ndim == 3 and image.shape[2] == 4:
                return np.ascontiguousarray(image[:, :, :3]).astype(np.uint8, copy=False)
            if image.ndim == 3 and image.shape[2] == 3:
                return image.astype(np.uint8, copy=False)
            raise ValueError(f"Unsupported ndarray shape: {image.shape!r}")
        raise TypeError(
            f"Unsupported image type: {type(image).__name__}. "
            "Expected PIL.Image.Image or numpy.ndarray."
        )

    @staticmethod
    def _parse_ground_truth(raw: Any) -> dict[str, Any]:
        """Donut datasets store ground_truth as a JSON string; parse robustly."""
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw}
            if isinstance(parsed, dict):
                return parsed
            return {"_raw": parsed}
        return {"_raw": str(raw)}
