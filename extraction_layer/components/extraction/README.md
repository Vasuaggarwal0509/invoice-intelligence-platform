# components/extraction

`OCRResult` → `ExtractionResult` (named header fields with confidence + provenance).

## Technique

- **G1 — regex / anchor matching** for numeric-format fields (`invoice_no`, `invoice_date`, `tax_id`, `iban`).
- **G2 — label-anchor dictionary** (variants like `Invoiceno`, `Taxld`) matched with `rapidfuzz`.
- **Column detection** on OCR bboxes to split left-column seller from right-column client, then multi-line aggregation + space-reinsertion normalisation.
- **Scaffolded alternative** — `layoutlmv3` backend (not implemented) for multi-template invoices.

## Use case

- Extract the header fields of a Donut-schema / Western-style invoice from OCR output — no ML training needed.

## Advantages

- Zero training data.
- < 5 ms / invoice on CPU.
- Every emitted field carries `source` + `source_detail`, so validators can weigh provenance.
- Works on any single-template dataset; graceful degrade if anchors missing (fields = `None`).

## Disadvantages

- Single-template assumption — drops accuracy on multi-template data (would need the LayoutLM fallback).
- `seller` / `client` F1 capped by OCR space-collapse + CamelCase brand names.
- No line-item extraction here (that's `components/tables/`).

## Inputs / Outputs

- **Input**: `OCRResult` from the OCR stage. See `schema/input.example.json`.
- **Output**: `ExtractionResult` — `fields: dict[str, ExtractedField]`. See `schema/output.example.json`.
- Schemas regenerable via `python -m tools.regen_schemas`.

## Run standalone

```python
from components.extraction import make_extractor
from components.ocr import make_ocr, InvoiceInput

ocr = make_ocr("rapidocr")
ex = make_extractor("heuristic")

with open("invoice.png", "rb") as f:
    ocr_result = ocr.ocr_invoice(InvoiceInput(
        id="inv-001", content_type="image/png", image_bytes=f.read(),
    ))

print(ex.extract(ocr_result).model_dump_json())
```

## Deploying as an independent service

Consumes `OCRResult` JSON; emits `ExtractionResult` JSON. Dependencies:
`pydantic`, `rapidfuzz`. Imports only `components._common` and
`components.ocr.types` — suitable for a separate service / lambda with
just those two packages vendored.
