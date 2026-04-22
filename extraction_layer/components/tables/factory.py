"""
Table-extractor factory — pick a backend by short name.
"""

import importlib
from typing import Any

from .base import BaseTableExtractor


_REGISTRY: dict[str, str] = {
    "spatial": "extraction_layer.components.tables.spatial.extractor.SpatialTableExtractor",
    "pp_structure": "extraction_layer.components.tables.pp_structure_backend.PPStructureTableExtractor",
    "layoutlm": "extraction_layer.components.tables.layoutlm_backend.LayoutLMTableExtractor",
}


def available_table_extractors() -> list[str]:
    return sorted(_REGISTRY.keys())


def make_table_extractor(name: str = "spatial", **kwargs: Any) -> BaseTableExtractor:
    """Instantiate a table-extractor backend by name.

    Args:
        name: One of :func:`available_table_extractors`. Default ``"spatial"``
            per the Component H path chosen in `research.md` §10 and
            `progress.md` 2026-04-18.
        **kwargs: Forwarded to the backend constructor.

    Raises:
        ValueError: Unknown backend key.
        NotImplementedError: Scaffolded backends raise when .extract is called.
    """
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown table extractor {name!r}. Available: {available_table_extractors()}"
        )
    module_path, class_name = _REGISTRY[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls: type[BaseTableExtractor] = getattr(module, class_name)
    return cls(**kwargs)
