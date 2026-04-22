"""Tests for the dataset factory."""

import pytest

from data_sources import available_datasets, make_dataset
from data_sources.base import BaseDataset


def test_available_datasets_includes_expected():
    names = available_datasets()
    assert "katanaml" in names
    assert "midd" in names
    assert "sroie" in names


def test_unknown_dataset_raises():
    with pytest.raises(ValueError):
        make_dataset("no-such-dataset")


def test_make_scaffolded_datasets_do_not_need_heavy_deps():
    # midd and sroie are scaffolded; their constructors must succeed without
    # any external library installed.
    for name in ("midd", "sroie"):
        ds = make_dataset(name)
        assert isinstance(ds, BaseDataset)
        assert ds.name == name
