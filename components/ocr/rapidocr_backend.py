"""
RapidOCR backend — the default OCR engine for the prototype.

Wraps PaddleOCR's PP-OCRv5 detection / angle-classification / recognition
models, executed through ONNX Runtime, with no PaddlePaddle dependency.
See `research.md` §3 for the full rationale; TL;DR: same model class as
PaddleOCR-direct, ~80 MB install, ~0.2 s/page on CPU, English-native docs,
avoids known PaddlePaddle install pain.

Install:
    pip install rapidocr-onnxruntime
"""

import io
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .base import BaseOCR, ImageInput
from .types import BoundingBox, Line, OCRResult, PageSize, Polygon, Token


class RapidOCRBackend(BaseOCR):
    """OCR backend backed by rapidocr-onnxruntime (PP-OCRv5 via ONNX)."""

    def __init__(self, **engine_kwargs: Any) -> None:
        """Initialise the RapidOCR engine.

        Args:
            engine_kwargs: Forwarded to ``rapidocr_onnxruntime.RapidOCR(...)``.
                Common knobs: ``text_score`` (minimum recognition confidence,
                default 0.5 in RapidOCR), ``use_det`` / ``use_cls`` / ``use_rec``
                (toggle sub-models). Passing nothing is fine; defaults are sane.

        Raises:
            ImportError: If ``rapidocr-onnxruntime`` is not installed.
        """
        try:
            from rapidocr_onnxruntime import RapidOCR as _RapidOCR
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "rapidocr-onnxruntime is not installed. "
                "Install with: pip install rapidocr-onnxruntime"
            ) from exc

        self._engine = _RapidOCR(**engine_kwargs)

    # ----- BaseOCR interface ------------------------------------------------

    @property
    def backend_name(self) -> str:
        return "rapidocr"

    def ocr(self, image: ImageInput) -> OCRResult:
        start = time.perf_counter()

        img_array = self._to_ndarray(image)
        page = PageSize(
            width=int(img_array.shape[1]),
            height=int(img_array.shape[0]),
        )

        raw_result = self._call_engine(img_array)

        lines: list[Line] = []
        all_tokens: list[Token] = []
        if raw_result:
            for detection in raw_result:
                polygon, text, score = self._unpack_detection(detection)
                if not text:
                    continue
                bbox = self._polygon_to_bbox(polygon)
                confidence = self._safe_score(score)
                line_tokens = self._split_line_into_tokens(
                    text=text,
                    bbox=bbox,
                    line_confidence=confidence,
                )
                line = Line(
                    text=text,
                    bbox=bbox,
                    polygon=polygon,
                    tokens=line_tokens,
                    confidence=confidence,
                )
                lines.append(line)
                all_tokens.extend(line_tokens)

        duration_ms = (time.perf_counter() - start) * 1000.0
        return OCRResult(
            tokens=all_tokens,
            lines=lines,
            page=page,
            backend=self.backend_name,
            duration_ms=duration_ms,
        )

    def warmup(self) -> None:
        """Run a cheap OCR call so the model loads before real traffic."""
        dummy = np.full((32, 128, 3), 255, dtype=np.uint8)
        try:
            self._engine(dummy)
        except Exception:
            # Warmup failures are informational — the real call will surface any issue.
            pass

    # ----- Engine call normalisation ---------------------------------------

    def _call_engine(self, img_array: np.ndarray) -> list[Any] | None:
        """Return a uniform list-of-detections regardless of RapidOCR version.

        RapidOCR's return shape has changed across releases:
          * older: ``(list_of_detections, elapse_float)``
          * newer: an object exposing ``.boxes`` / ``.txts`` / ``.scores``
          * both : ``(None, elapse)`` when nothing detected

        This method collapses those into ``list_of_detections | None``.
        """
        result = self._engine(img_array)
        if result is None:
            return None
        if isinstance(result, tuple) and len(result) >= 1:
            detections = result[0]
            return list(detections) if detections is not None else None
        # Newer object-based API
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is not None and txts is not None and scores is not None:
            return [list(triple) for triple in zip(boxes, txts, scores)]
        return None

    @staticmethod
    def _unpack_detection(detection: Any) -> tuple[Polygon, str, float]:
        """Unpack one RapidOCR detection into ``(polygon, text, score)``."""
        if not isinstance(detection, (list, tuple)) or len(detection) != 3:
            raise ValueError(f"Unexpected RapidOCR detection shape: {detection!r}")
        raw_polygon, raw_text, raw_score = detection
        polygon: Polygon = [[float(p[0]), float(p[1])] for p in raw_polygon]
        text = str(raw_text) if raw_text is not None else ""
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        return polygon, text, score

    # ----- Input normalisation ---------------------------------------------

    @staticmethod
    def _to_ndarray(image: ImageInput) -> np.ndarray:
        """Normalise any supported image input to an HxWx3 uint8 ndarray."""
        if isinstance(image, np.ndarray):
            if image.ndim == 2:
                # Grayscale -> RGB
                return np.stack([image] * 3, axis=-1).astype(np.uint8, copy=False)
            if image.ndim == 3 and image.shape[2] == 4:
                # RGBA -> RGB (drop alpha)
                return np.ascontiguousarray(image[:, :, :3]).astype(np.uint8, copy=False)
            if image.ndim == 3 and image.shape[2] == 3:
                return image.astype(np.uint8, copy=False)
            raise ValueError(f"Unsupported ndarray shape for image: {image.shape!r}")
        if isinstance(image, (str, Path)):
            with Image.open(image) as pil_img:
                return np.array(pil_img.convert("RGB"))
        if isinstance(image, (bytes, bytearray)):
            with Image.open(io.BytesIO(bytes(image))) as pil_img:
                return np.array(pil_img.convert("RGB"))
        raise TypeError(
            f"Unsupported image input type: {type(image).__name__}. "
            "Expected str, Path, bytes, or numpy.ndarray."
        )

    # ----- Geometry helpers -------------------------------------------------

    @staticmethod
    def _polygon_to_bbox(polygon: Polygon) -> BoundingBox:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))

    @staticmethod
    def _safe_score(raw: float) -> float:
        """Clamp to [0, 1] and coerce NaN to 0.0."""
        if raw is None or (isinstance(raw, float) and math.isnan(raw)):
            return 0.0
        return max(0.0, min(1.0, float(raw)))

    @staticmethod
    def _split_line_into_tokens(
        text: str,
        bbox: BoundingBox,
        line_confidence: float,
    ) -> list[Token]:
        """Derive word-level tokens from a line by whitespace splitting.

        Each word's bbox is a proportional horizontal slice of the line bbox,
        sized by the word's character count (spaces included between words).
        This is a first-order approximation suited to horizontal printed text;
        rotated text keeps an accurate line polygon but axis-aligned tokens.
        """
        words = text.split()
        if not words:
            return []

        total_chars = sum(len(w) for w in words) + max(0, len(words) - 1)
        if total_chars == 0:
            return []

        x0, y0, x1, y1 = bbox.x0, bbox.y0, bbox.x1, bbox.y1
        width = x1 - x0
        cursor = 0
        tokens: list[Token] = []
        for word in words:
            start = cursor
            end = cursor + len(word)
            tx0 = x0 + (start / total_chars) * width
            tx1 = x0 + (end / total_chars) * width
            token_bbox = BoundingBox(x0=tx0, y0=y0, x1=tx1, y1=y1)
            token_polygon: Polygon = [
                [tx0, y0],
                [tx1, y0],
                [tx1, y1],
                [tx0, y1],
            ]
            tokens.append(
                Token(
                    text=word,
                    bbox=token_bbox,
                    polygon=token_polygon,
                    confidence=line_confidence,
                )
            )
            cursor = end + 1  # +1 for the whitespace between words
        return tokens
