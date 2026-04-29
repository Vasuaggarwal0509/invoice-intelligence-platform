"""Tests that scaffolded datasets are importable but not runnable.

Mirrors the OCR scaffolded-backend tests — enforces the "swap path visible
from day one" property from `project.md` §8.0. If a scaffolded loader starts
needing heavy dependencies at import / __init__ time, these tests fail and
we correct the drift.
"""

import pytest

from extraction_layer.data_sources.base import BaseDataset
from extraction_layer.data_sources.midd.loader import MIDDDataset
from extraction_layer.data_sources.sroie.loader import SROIEDataset

SCAFFOLDED = [
    pytest.param(MIDDDataset, "midd", id="midd"),
    pytest.param(SROIEDataset, "sroie", id="sroie"),
]


@pytest.mark.parametrize("ds_cls, expected_name", SCAFFOLDED)
def test_scaffolded_dataset_instantiates(ds_cls, expected_name):
    ds = ds_cls()
    assert isinstance(ds, BaseDataset)
    assert ds.name == expected_name


@pytest.mark.parametrize("ds_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_dataset_accepts_forward_kwargs(ds_cls, _expected_name):
    ds_cls(some_future_option=True, another=42)


@pytest.mark.parametrize("ds_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_dataset_load_raises(ds_cls, _expected_name):
    ds = ds_cls()
    with pytest.raises(NotImplementedError):
        list(ds.load("train"))


@pytest.mark.parametrize("ds_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_dataset_get_raises(ds_cls, _expected_name):
    ds = ds_cls()
    with pytest.raises(NotImplementedError):
        ds.get("train", 0)


@pytest.mark.parametrize("ds_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_dataset_count_raises(ds_cls, _expected_name):
    ds = ds_cls()
    with pytest.raises(NotImplementedError):
        ds.count("train")


@pytest.mark.parametrize("ds_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_dataset_exposes_splits_without_raising(ds_cls, _expected_name):
    # splits is a property the real implementation will replace; today it is
    # a placeholder. We just check it does not raise and is a list.
    ds = ds_cls()
    assert isinstance(ds.splits, list)
