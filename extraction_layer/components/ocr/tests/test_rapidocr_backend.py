"""
End-to-end tests for the RapidOCR backend.

These tests load the real PP-OCRv5 models via rapidocr-onnxruntime, so each
test in this module incurs model-load cost the first time. They are marked
``ocr_heavy`` so they can be deselected with:

    pytest -m "not ocr_heavy" components/ocr/tests

Requires:
    pip install rapidocr-onnxruntime pillow
"""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from extraction_layer.components.ocr.types import OCRResult


# Skip the whole module if RapidOCR isn't installed — lets test_types and
# test_base still run in minimal envs.
pytest.importorskip(
    "rapidocr_onnxruntime",
    reason="rapidocr-onnxruntime not installed; skip RapidOCR integration tests",
)

from extraction_layer.components.ocr.rapidocr_backend import RapidOCRBackend  # noqa: E402
from extraction_layer.components.ocr.types import BoundingBox  # noqa: E402


pytestmark = pytest.mark.ocr_heavy


# ----- Fixtures ------------------------------------------------------------


@pytest.fixture(scope="module")
def backend() -> RapidOCRBackend:
    return RapidOCRBackend()


@pytest.fixture(scope="module")
def invoice_like_image() -> Image.Image:
    """Render a simple invoice-like image with clear, large printed text."""
    img = Image.new("RGB", (640, 240), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=36)
    except TypeError:  # pragma: no cover - very old Pillow without size arg
        font = ImageFont.load_default()
    draw.text((30, 40), "INVOICE 12345", fill="black", font=font)
    draw.text((30, 120), "TOTAL 1000", fill="black", font=font)
    return img


# ----- Tests ---------------------------------------------------------------


def test_ocr_returns_valid_result_from_ndarray(backend, invoice_like_image):
    arr = np.array(invoice_like_image)
    result = backend.ocr(arr)

    assert isinstance(result, OCRResult)
    assert result.backend == "rapidocr"
    assert result.page.width == arr.shape[1]
    assert result.page.height == arr.shape[0]
    assert result.duration_ms > 0


def test_ocr_from_file_path(backend, invoice_like_image, tmp_path: Path):
    path = tmp_path / "invoice_like.png"
    invoice_like_image.save(path)
    result = backend.ocr(str(path))
    assert isinstance(result, OCRResult)


def test_ocr_from_bytes(backend, invoice_like_image):
    buf = io.BytesIO()
    invoice_like_image.save(buf, format="PNG")
    result = backend.ocr(buf.getvalue())
    assert isinstance(result, OCRResult)


def test_ocr_from_path_object(backend, invoice_like_image, tmp_path: Path):
    path = tmp_path / "invoice_like.png"
    invoice_like_image.save(path)
    result = backend.ocr(path)
    assert isinstance(result, OCRResult)


def test_ocr_detects_something_from_printed_text(backend, invoice_like_image):
    """Soft assertion: OCR should return at least one line from clean printed text.

    This is a sanity check that the engine is wired up and models load — not a
    strict accuracy assertion (accuracy is measured by the evaluation harness
    on the real dataset, not here).
    """
    arr = np.array(invoice_like_image)
    result = backend.ocr(arr)
    assert (
        len(result.lines) >= 1
    ), "Expected at least one detected line from clearly-rendered printed text"


def test_tokens_are_derived_from_lines(backend, invoice_like_image):
    arr = np.array(invoice_like_image)
    result = backend.ocr(arr)

    for line in result.lines:
        # Every line produces at least one token (even one-word lines)
        assert len(line.tokens) >= 1
        # Every word in the line.text should appear verbatim among its tokens
        for word in line.text.split():
            assert any(
                t.text == word for t in line.tokens
            ), f"Word {word!r} missing from tokens of line {line.text!r}"

    # OCRResult.tokens == flatten(line.tokens for line in lines)
    flat_tokens = [t for line in result.lines for t in line.tokens]
    assert len(flat_tokens) == len(result.tokens)


def test_token_bboxes_are_within_line_bbox(backend, invoice_like_image):
    arr = np.array(invoice_like_image)
    result = backend.ocr(arr)
    for line in result.lines:
        lbb = line.bbox
        for token in line.tokens:
            tbb = token.bbox
            # Allow a small floating-point slack
            slack = 1e-6
            assert tbb.x0 >= lbb.x0 - slack
            assert tbb.x1 <= lbb.x1 + slack
            assert tbb.y0 >= lbb.y0 - slack
            assert tbb.y1 <= lbb.y1 + slack


def test_empty_image_is_safe(backend):
    white = np.full((120, 320, 3), 255, dtype=np.uint8)
    result = backend.ocr(white)
    assert isinstance(result, OCRResult)
    assert result.page.width == 320
    assert result.page.height == 120
    # Either nothing detected, or whatever is detected has valid confidences.
    for line in result.lines:
        assert 0.0 <= line.confidence <= 1.0


def test_grayscale_input_is_coerced(backend, invoice_like_image):
    gray = np.array(invoice_like_image.convert("L"))
    assert gray.ndim == 2
    result = backend.ocr(gray)
    assert isinstance(result, OCRResult)


def test_rgba_input_is_coerced(backend, invoice_like_image):
    rgba = np.array(invoice_like_image.convert("RGBA"))
    assert rgba.shape[2] == 4
    result = backend.ocr(rgba)
    assert isinstance(result, OCRResult)


def test_rejects_unsupported_input_type(backend):
    with pytest.raises(TypeError):
        backend.ocr(object())  # type: ignore[arg-type]


def test_warmup_runs_without_raising(backend):
    backend.warmup()


# ----- Static helper tests (no model load) ---------------------------------


def test_split_line_into_tokens_single_word():
    bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
    tokens = RapidOCRBackend._split_line_into_tokens(
        text="INVOICE", bbox=bbox, line_confidence=0.9
    )
    assert len(tokens) == 1
    assert tokens[0].text == "INVOICE"
    assert tokens[0].bbox.as_tuple() == (0.0, 0.0, 100.0, 20.0)


def test_split_line_into_tokens_two_words_proportional():
    bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
    tokens = RapidOCRBackend._split_line_into_tokens(
        text="AB CD", bbox=bbox, line_confidence=0.8
    )
    assert [t.text for t in tokens] == ["AB", "CD"]
    # total chars = 2 + 2 + 1(space) = 5
    # AB: 0..2/5 = 0..40 ; CD: 3..5/5 = 60..100
    assert tokens[0].bbox.x0 == pytest.approx(0.0)
    assert tokens[0].bbox.x1 == pytest.approx(40.0)
    assert tokens[1].bbox.x0 == pytest.approx(60.0)
    assert tokens[1].bbox.x1 == pytest.approx(100.0)


def test_split_empty_line_returns_no_tokens():
    bbox = BoundingBox(x0=0, y0=0, x1=100, y1=20)
    tokens = RapidOCRBackend._split_line_into_tokens(
        text="", bbox=bbox, line_confidence=0.5
    )
    assert tokens == []


def test_safe_score_clamps_and_handles_nan():
    assert RapidOCRBackend._safe_score(0.5) == 0.5
    assert RapidOCRBackend._safe_score(-0.1) == 0.0
    assert RapidOCRBackend._safe_score(1.5) == 1.0
    assert RapidOCRBackend._safe_score(float("nan")) == 0.0


def test_polygon_to_bbox():
    polygon = [[10, 5], [100, 5], [100, 25], [10, 25]]
    bbox = RapidOCRBackend._polygon_to_bbox(polygon)
    assert bbox.as_tuple() == (10.0, 5.0, 100.0, 25.0)
