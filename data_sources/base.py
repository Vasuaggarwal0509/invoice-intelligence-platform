"""
data_sources — abstract dataset interface.

All dataset loaders (Katanaml, MIDD, SROIE, ...) inherit from `BaseDataset`
and emit `Sample`s. Downstream stages consume only `Sample` + the
dataset-specific raw ground_truth dict — they never branch on which loader
produced the sample.

Adding a new dataset:
    1. Create `data_sources/<name>/loader.py` with a subclass of BaseDataset.
    2. Implement the abstract methods.
    3. Register the dotted class path in `data_sources/factory.py`.
    4. Add tests under `data_sources/tests/`.
"""

from abc import ABC, abstractmethod
from typing import Iterator

from .types import Sample


class BaseDataset(ABC):
    """Abstract dataset loader.

    Concrete loaders may do heavy work in ``__init__`` (e.g. download + cache
    a HuggingFace dataset) or lazily; that is an implementation choice.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in Sample.source_dataset."""
        raise NotImplementedError

    @property
    @abstractmethod
    def splits(self) -> list[str]:
        """Available splits, e.g. ['train', 'validation', 'test']."""
        raise NotImplementedError

    @abstractmethod
    def load(self, split: str) -> Iterator[Sample]:
        """Iterate over all samples in a split (streaming-friendly)."""
        raise NotImplementedError

    @abstractmethod
    def get(self, split: str, index: int) -> Sample:
        """Fetch one sample by split + integer index."""
        raise NotImplementedError

    @abstractmethod
    def count(self, split: str) -> int:
        """Number of samples in a given split."""
        raise NotImplementedError

    def __len__(self) -> int:
        """Total samples across all splits."""
        return sum(self.count(s) for s in self.splits)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} name='{self.name}' splits={self.splits}>"
