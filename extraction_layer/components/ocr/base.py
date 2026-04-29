"""
OCR component — abstract backend interface.

All concrete OCR backends inherit from `BaseOCR`. Upstream and downstream
pipeline stages depend only on the `OCRResult` output schema in `types.py`
and never branch on which backend produced the result.

Adding a new backend:
    1. Create `components/ocr/<backend>_backend.py` with a subclass of BaseOCR.
    2. Implement `ocr(image)` returning an OCRResult.
    3. Implement the `backend_name` property.
    4. Register the import path in `components/ocr/factory.py`.
    5. Add a test in `components/ocr/tests/`.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

import numpy as np

from .types import InvoiceInput, OCRResult

# Every concrete backend must accept at least these input types. Individual
# backends can coerce them to the format their underlying library wants.
ImageInput = Union[str, Path, bytes, np.ndarray]


class BaseOCR(ABC):
    """Abstract OCR backend.

    Concrete backends should lazy-import heavy dependencies inside ``__init__``
    so that importing this module (or a sibling module) does not pull in the
    full OCR runtime.

    Two entry points:
      * :meth:`ocr` — lenient single-image call; accepts a path, bytes, or
        ndarray. Good for scripts, tests, and the in-process pipeline.
      * :meth:`ocr_invoice` — **service-boundary** call that takes an
        :class:`InvoiceInput` (bytes or URI + metadata). Use this when the
        component is deployed as an independent service so the wire format
        stays explicit.
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Short identifier stored in OCRResult.backend and processing logs."""
        raise NotImplementedError

    @abstractmethod
    def ocr(self, image: ImageInput) -> OCRResult:
        """Run OCR on one image.

        Args:
            image: File path, bytes, or numpy array (H, W) or (H, W, 3) /
                (H, W, 4). Backends coerce to their native format.

        Returns:
            OCRResult — see components/ocr/types.py for the full schema.
        """
        raise NotImplementedError

    def ocr_invoice(self, input: InvoiceInput) -> OCRResult:
        """Run OCR on a service-boundary :class:`InvoiceInput`.

        Default implementation unwraps ``input.image_bytes`` and delegates
        to :meth:`ocr`. Subclasses only need to override this if they want
        to pull bytes from ``input.image_uri`` themselves (e.g. to stream
        directly from S3 without materialising locally).

        Raises:
            NotImplementedError: If the input uses ``image_uri`` and this
                backend has not implemented URI fetching.
        """
        if input.image_bytes is not None:
            return self.ocr(input.image_bytes)
        # image_uri branch — default impl refuses; backends override as needed.
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support `image_uri` inputs. "
            "Either pass `image_bytes` or override `ocr_invoice` in the backend."
        )

    def warmup(self) -> None:
        """Trigger model load ahead of real traffic. Default is no-op.

        Override in backends where the first call is substantially slower than
        subsequent ones (most OCR libraries lazy-load model weights).
        """
        return None

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} backend='{self.backend_name}'>"
