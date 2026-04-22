"""data_sources — dataset loaders that feed the pipeline.

Public surface:

    from data_sources import make_dataset

    ds = make_dataset("katanaml")           # primary PoC dataset
    for sample in ds.load("test"):
        ...  # sample.image, sample.ground_truth

See README.md for the supported datasets and the add-a-dataset recipe.
"""

from .base import BaseDataset
from .factory import available_datasets, make_dataset
from .types import Sample

__all__ = [
    "BaseDataset",
    "Sample",
    "available_datasets",
    "make_dataset",
]
