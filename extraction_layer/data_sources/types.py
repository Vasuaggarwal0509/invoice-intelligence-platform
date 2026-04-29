"""
Shared types for dataset loaders.

A `Sample` represents one datum in the pipeline's training/evaluation view:
an image plus whatever structured ground truth the source dataset provided.
Each concrete dataset loader emits `Sample`s; downstream stages (OCR,
extraction, validation, evaluation) consume them uniformly.
"""

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Sample(BaseModel):
    """One (image, ground_truth) pair from a dataset.

    `ground_truth` is intentionally a plain ``dict`` because the schema varies
    across datasets (Katanaml vs MIDD vs SROIE). Loaders may expose typed
    accessors for their specific schema (see ``KatanamlInvoicesDataset`` for
    an example).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    id: str = Field(..., min_length=1, description="Unique identifier within the dataset")
    image: np.ndarray = Field(..., description="HxWx3 RGB uint8")
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    split: str = Field(..., min_length=1, description="e.g. 'train' | 'validation' | 'test'")
    source_dataset: str = Field(
        ..., min_length=1, description="Dataset name, e.g. 'katanaml-invoices-donut-v1'"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v: np.ndarray) -> np.ndarray:
        if v.ndim != 3:
            raise ValueError(f"image must be 3-dimensional (HxWx3), got ndim={v.ndim}")
        if v.shape[2] != 3:
            raise ValueError(
                f"image must have 3 channels (RGB), got shape={v.shape}. "
                "Convert in the loader before constructing the Sample."
            )
        if v.dtype != np.uint8:
            raise ValueError(f"image must be uint8, got dtype={v.dtype}")
        return v
