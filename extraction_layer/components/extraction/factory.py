"""
Extractor factory — pick a backend by short name.
"""

import importlib
from typing import Any

from .base import BaseExtractor

_REGISTRY: dict[str, str] = {
    "heuristic": "extraction_layer.components.extraction.heuristic.extractor.HeuristicExtractor",
    "layoutlmv3": "extraction_layer.components.extraction.layoutlm_backend.LayoutLMv3Extractor",
}


def available_extractors() -> list[str]:
    return sorted(_REGISTRY.keys())


def make_extractor(name: str = "heuristic", **kwargs: Any) -> BaseExtractor:
    """Instantiate an extractor backend by name.

    Args:
        name: One of :func:`available_extractors`. Default ``"heuristic"``
            per the chosen Component G path (`progress.md` 2026-04-18).
        **kwargs: Forwarded to the backend constructor.

    Raises:
        ValueError: Unknown backend key.
        NotImplementedError: Scaffolded backends raise when .extract is called.
    """
    if name not in _REGISTRY:
        raise ValueError(f"Unknown extractor {name!r}. Available: {available_extractors()}")
    module_path, class_name = _REGISTRY[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls: type[BaseExtractor] = getattr(module, class_name)
    return cls(**kwargs)
