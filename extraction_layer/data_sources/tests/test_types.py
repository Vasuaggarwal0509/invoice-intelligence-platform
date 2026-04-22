"""Tests for the Sample type."""

import numpy as np
import pytest
from pydantic import ValidationError

from extraction_layer.data_sources.types import Sample


def _dummy_image(h: int = 32, w: int = 32) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


class TestSample:
    def test_valid_sample(self):
        img = _dummy_image()
        sample = Sample(
            id="ds-001",
            image=img,
            ground_truth={"invoice_no": "INV-1"},
            split="train",
            source_dataset="katanaml-invoices-donut-v1",
        )
        assert sample.id == "ds-001"
        assert sample.image.shape == (32, 32, 3)
        assert sample.ground_truth["invoice_no"] == "INV-1"
        assert sample.metadata == {}

    def test_id_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            Sample(
                id="",
                image=_dummy_image(),
                ground_truth={},
                split="train",
                source_dataset="x",
            )

    def test_split_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            Sample(
                id="a",
                image=_dummy_image(),
                ground_truth={},
                split="",
                source_dataset="x",
            )

    def test_source_dataset_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            Sample(
                id="a",
                image=_dummy_image(),
                ground_truth={},
                split="train",
                source_dataset="",
            )

    def test_image_must_be_3d(self):
        with pytest.raises(ValidationError):
            Sample(
                id="a",
                image=np.zeros((32, 32), dtype=np.uint8),  # grayscale
                ground_truth={},
                split="train",
                source_dataset="x",
            )

    def test_image_must_have_3_channels(self):
        with pytest.raises(ValidationError):
            Sample(
                id="a",
                image=np.zeros((32, 32, 4), dtype=np.uint8),  # RGBA
                ground_truth={},
                split="train",
                source_dataset="x",
            )

    def test_image_must_be_uint8(self):
        with pytest.raises(ValidationError):
            Sample(
                id="a",
                image=np.zeros((32, 32, 3), dtype=np.float32),
                ground_truth={},
                split="train",
                source_dataset="x",
            )

    def test_frozen(self):
        sample = Sample(
            id="a",
            image=_dummy_image(),
            ground_truth={},
            split="train",
            source_dataset="x",
        )
        with pytest.raises((ValidationError, TypeError)):
            sample.id = "b"

    def test_metadata_defaults_to_empty_dict(self):
        sample = Sample(
            id="a",
            image=_dummy_image(),
            ground_truth={},
            split="train",
            source_dataset="x",
        )
        assert sample.metadata == {}

    def test_metadata_accepts_arbitrary_content(self):
        sample = Sample(
            id="a",
            image=_dummy_image(),
            ground_truth={},
            split="train",
            source_dataset="x",
            metadata={"note": "bench", "row_index": 42},
        )
        assert sample.metadata["row_index"] == 42
