"""
End-to-end tests for KatanamlInvoicesDataset.

These tests touch the real HuggingFace dataset — on first run they download
the Katanaml dataset (~few-hundred-MB cache) under ``data/katanaml/``. They
are marked ``dataset_heavy`` so they can be deselected with:

    pytest -m "not dataset_heavy" data_sources/tests
"""

import numpy as np
import pytest


# Skip the whole module if the HF datasets library is not installed.
pytest.importorskip(
    "datasets",
    reason="HuggingFace 'datasets' library not installed; skip dataset integration tests",
)

from extraction_layer.data_sources.katanaml_invoices.loader import KatanamlInvoicesDataset  # noqa: E402
from extraction_layer.data_sources.types import Sample  # noqa: E402


pytestmark = pytest.mark.dataset_heavy


# Expected counts per research.md §4.1 (501 total = 425 + 50 + 26).
EXPECTED_SIZES = {
    "train": 425,
    "validation": 50,
    "test": 26,
}


@pytest.fixture(scope="module")
def dataset() -> KatanamlInvoicesDataset:
    # Default cache_dir = data/katanaml/ relative to cwd.
    return KatanamlInvoicesDataset()


def test_dataset_has_expected_name(dataset):
    assert dataset.name == "katanaml-invoices-donut-v1"


def test_dataset_has_three_splits(dataset):
    assert set(dataset.splits) == set(EXPECTED_SIZES.keys())


@pytest.mark.parametrize("split,expected", list(EXPECTED_SIZES.items()))
def test_split_counts_match_research(dataset, split, expected):
    assert dataset.count(split) == expected


def test_total_length(dataset):
    assert len(dataset) == sum(EXPECTED_SIZES.values())


def test_get_returns_valid_sample(dataset):
    sample = dataset.get("test", 0)
    assert isinstance(sample, Sample)
    assert sample.split == "test"
    assert sample.source_dataset == "katanaml-invoices-donut-v1"
    assert sample.id == "katanaml-test-00000"
    assert sample.image.shape[2] == 3
    assert sample.image.dtype == np.uint8
    # Ground truth should be parsed into a dict.
    assert isinstance(sample.ground_truth, dict)
    assert sample.metadata["row_index"] == 0


def test_ground_truth_has_donut_header(dataset):
    sample = dataset.get("test", 0)
    header = KatanamlInvoicesDataset.header_of(sample)
    assert isinstance(header, dict)
    # Research §4.1 documented these fields; at least one header key is expected.
    plausible_keys = {"invoice_no", "invoice_date", "seller", "client"}
    assert plausible_keys.intersection(header.keys()), (
        f"Expected at least one of {plausible_keys} in header, got keys {list(header.keys())}"
    )


def test_items_accessor_returns_list(dataset):
    sample = dataset.get("test", 0)
    items = KatanamlInvoicesDataset.items_of(sample)
    assert isinstance(items, list)


def test_load_iterates_all_samples_in_split(dataset):
    seen_ids = []
    for sample in dataset.load("test"):
        seen_ids.append(sample.id)
    assert len(seen_ids) == EXPECTED_SIZES["test"]
    assert len(set(seen_ids)) == len(seen_ids)  # unique


def test_unknown_split_raises_on_get(dataset):
    with pytest.raises(ValueError):
        dataset.get("nosuchsplit", 0)


def test_unknown_split_raises_on_count(dataset):
    with pytest.raises(ValueError):
        dataset.count("nosuchsplit")


def test_out_of_range_index_raises(dataset):
    with pytest.raises(IndexError):
        dataset.get("test", EXPECTED_SIZES["test"] + 100)
