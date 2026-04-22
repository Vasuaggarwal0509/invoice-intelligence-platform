# components/tables

`OCRResult` → `TableExtractionResult` (per-invoice `items` array).

## Technique

- **Spatial clustering** on OCR line bboxes:
  1. Find `ITEMS` / `SUMMARY` anchors (variants from `components/_common/invoice_anchors.py`).
  2. Detect item anchors — leftmost column, text matching `\d+\.`.
  3. For each anchor, bucket same-y-band lines → classify by value pattern (decimal, percent, UM-filler, description text).
  4. Sort decimals by x → Qty / Net price / Net worth / Gross worth.
  5. Aggregate description continuation lines below the anchor band.
- **Scaffolded alternatives** — `pp_structure` (PP-StructureV3 table model) and `layoutlm`.

## Use case

- Recover the per-item array (`qty`, `net_price`, `net_worth`, `vat`, `gross_worth`, `desc`) from an OCR'd invoice — single-template datasets in particular.

## Advantages

- < 1 ms / invoice on CPU.
- No model / training — value-pattern classification + bbox geometry.
- Independent of extraction (uses only shared `_common` utilities).

## Disadvantages

- Single-template assumption — column x-ranges expected to be consistent within a dataset.
- Cannot split uppercase-run merges like `DPOAP69387` (no case boundary).
- Relies on ITEMS / SUMMARY anchors — no items table is emitted if either is missing.

## Inputs / Outputs

- **Input**: `OCRResult`. See `schema/input.example.json`.
- **Output**: `TableExtractionResult` with `items: list[InvoiceItem]`. See `schema/output.example.json`.
- Schemas regenerable via `python -m tools.regen_schemas`.

## Run standalone

```python
from components.tables import make_table_extractor
from components.ocr import make_ocr, InvoiceInput

ocr = make_ocr("rapidocr")
tex = make_table_extractor("spatial")

with open("invoice.png", "rb") as f:
    ocr_result = ocr.ocr_invoice(InvoiceInput(
        id="inv-001", content_type="image/png", image_bytes=f.read(),
    ))

print(tex.extract(ocr_result).model_dump_json())
```

## Deploying as an independent service

Consumes `OCRResult` JSON; emits `TableExtractionResult` JSON.
Dependencies: `pydantic`, `rapidfuzz`. Imports only `components._common`
and `components.ocr.types` — splittable into its own service with those
two vendored in.
