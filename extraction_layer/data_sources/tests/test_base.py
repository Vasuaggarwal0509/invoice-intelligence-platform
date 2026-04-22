"""Tests for the BaseDataset abstract interface."""

import pytest

from extraction_layer.data_sources.base import BaseDataset
from extraction_layer.data_sources.types import Sample


def _img():
    import numpy as np
    return np.full((8, 8, 3), 255, dtype=np.uint8)


def test_basedataset_is_abstract():
    with pytest.raises(TypeError):
        BaseDataset()  # type: ignore[abstract]


def test_subclass_missing_method_cannot_instantiate():
    class OnlyName(BaseDataset):
        @property
        def name(self) -> str:
            return "x"

    with pytest.raises(TypeError):
        OnlyName()  # type: ignore[abstract]


def test_fully_implemented_subclass_works():
    class TinyDataset(BaseDataset):
        def __init__(self):
            self._samples = {
                "train": [
                    Sample(
                        id=f"t-{i}",
                        image=_img(),
                        ground_truth={"i": i},
                        split="train",
                        source_dataset="tiny",
                    )
                    for i in range(3)
                ],
                "test": [
                    Sample(
                        id=f"e-{i}",
                        image=_img(),
                        ground_truth={"i": i},
                        split="test",
                        source_dataset="tiny",
                    )
                    for i in range(2)
                ],
            }

        @property
        def name(self) -> str:
            return "tiny"

        @property
        def splits(self) -> list[str]:
            return list(self._samples.keys())

        def load(self, split):
            yield from self._samples[split]

        def get(self, split, index):
            return self._samples[split][index]

        def count(self, split):
            return len(self._samples[split])

    ds = TinyDataset()
    assert ds.name == "tiny"
    assert sorted(ds.splits) == ["test", "train"]
    assert ds.count("train") == 3
    assert ds.count("test") == 2
    # __len__ default aggregates across splits
    assert len(ds) == 5
    # load iterator works
    samples = list(ds.load("train"))
    assert len(samples) == 3
    assert samples[0].id == "t-0"
    # get by index works
    assert ds.get("test", 1).id == "e-1"
