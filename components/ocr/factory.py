"""
OCR backend factory.

Centralises backend instantiation so callers can pick a backend by string
name (e.g. from a config file or environment variable) without importing
each concrete backend directly. Backends are imported lazily so unused
backends never pay their import cost.
"""

import importlib
from typing import Any

from .base import BaseOCR


# Maps a short backend key to the dotted path of its class. Lazy-imported.
_BACKEND_REGISTRY: dict[str, str] = {
    "rapidocr": "components.ocr.rapidocr_backend.RapidOCRBackend",
    "tesseract": "components.ocr.tesseract_backend.TesseractBackend",
    "paddleocr": "components.ocr.paddleocr_backend.PaddleOCRBackend",
    "doctr": "components.ocr.doctr_backend.DocTRBackend",
}


def available_backends() -> list[str]:
    """Return the list of known backend keys, sorted."""
    return sorted(_BACKEND_REGISTRY.keys())


def make_ocr(backend: str = "rapidocr", **kwargs: Any) -> BaseOCR:
    """Instantiate an OCR backend by short name.

    Args:
        backend: One of :func:`available_backends`. Defaults to ``"rapidocr"``,
            the prototype's default per `project.md` §2.1.
        **kwargs: Forwarded to the backend's constructor.

    Returns:
        A concrete :class:`BaseOCR` instance.

    Raises:
        ValueError: If ``backend`` is not a known key.
        ImportError: If the underlying OCR library is not installed.
    """
    if backend not in _BACKEND_REGISTRY:
        raise ValueError(
            f"Unknown OCR backend {backend!r}. Available: {available_backends()}"
        )

    module_path, class_name = _BACKEND_REGISTRY[backend].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls: type[BaseOCR] = getattr(module, class_name)
    return cls(**kwargs)
