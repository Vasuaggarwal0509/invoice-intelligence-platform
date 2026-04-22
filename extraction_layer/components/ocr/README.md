# components/ocr

Image bytes → `OCRResult` (lines + tokens + bboxes + page size).

## Technique

- **Default**: PaddleOCR PP-OCRv5 via ONNX Runtime (backend key `rapidocr`).
- **Alternatives scaffolded**: Tesseract, PaddleOCR-direct, docTR.
- Swappable via `make_ocr(name)` behind the `BaseOCR` ABC.

## Use case

- Any single invoice image (PNG / JPEG / PDF-page / TIFF) → structured text + layout, ready for the next pipeline stage.

## Advantages

- CPU-only, no GPU needed.
- ~80 MB install, no PaddlePaddle dependency.
- 106 languages including Devanagari (future Indian data).
- Pure data-out wire contract — downstream consumers need only the `OCRResult` JSON.

## Disadvantages

- ~5–7 s / page at 300 DPI A4 on CPU (image downscaling is a held optimisation).
- OCR character confusions (S↔5, I↔l) not self-corrected.
- First call incurs ~1 s model-load — call `.warmup()` at worker start.

## Inputs / Outputs

- **Input**: `InvoiceInput` — `id`, `content_type`, one of (`image_bytes` | `image_uri`), optional `filename`, free `metadata`. See `schema/input.example.json`.
- **Output**: `OCRResult`. See `schema/output.example.json`.
- JSON Schemas are generated from the Pydantic types. Regenerate with `python -m tools.regen_schemas`.

## Run standalone

```python
from components.ocr import make_ocr, InvoiceInput

ocr = make_ocr("rapidocr")
ocr.warmup()

with open("invoice.png", "rb") as f:
    result = ocr.ocr_invoice(InvoiceInput(
        id="inv-001",
        content_type="image/png",
        image_bytes=f.read(),
    ))

print(result.model_dump_json())
```

## Deploying as an independent service

`ocr_invoice(InvoiceInput) -> OCRResult` is the service-boundary method.
Dependencies: `rapidocr-onnxruntime`, `pydantic`, `numpy`, `pillow`. No
imports from other components. A future HTTP wrapper or AWS Lambda just
(de)serialises the `InvoiceInput` and `OCRResult` JSONs at the edges.
