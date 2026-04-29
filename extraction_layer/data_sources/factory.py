"""
Dataset factory.

Centralises loader instantiation so callers can pick a dataset by short
name (from config, CLI flag, env var). Loaders are lazy-imported so unused
implementations do not pay their import cost.
"""

import importlib
from typing import Any

from .base import BaseDataset

_REGISTRY: dict[str, str] = {
    "katanaml": "extraction_layer.data_sources.katanaml_invoices.loader.KatanamlInvoicesDataset",
    "midd": "extraction_layer.data_sources.midd.loader.MIDDDataset",
    "sroie": "extraction_layer.data_sources.sroie.loader.SROIEDataset",
}


def available_datasets() -> list[str]:
    """Return the list of known dataset keys, sorted."""
    return sorted(_REGISTRY.keys())


def make_dataset(name: str = "katanaml", **kwargs: Any) -> BaseDataset:
    """Instantiate a dataset loader by short name.

    Args:
        name: One of :func:`available_datasets`. Default ``"katanaml"``
            (the prototype's primary dataset per `project.md` §6).
        **kwargs: Forwarded to the concrete loader's constructor.

    Returns:
        A concrete :class:`BaseDataset` instance.

    Raises:
        ValueError: Unknown dataset name.
        ImportError: Underlying library (e.g. huggingface ``datasets``) not installed.
        NotImplementedError: Scaffolded datasets raise when methods are called.
    """
    if name not in _REGISTRY:
        raise ValueError(f"Unknown dataset {name!r}. Available: {available_datasets()}")

    module_path, class_name = _REGISTRY[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls: type[BaseDataset] = getattr(module, class_name)
    return cls(**kwargs)
