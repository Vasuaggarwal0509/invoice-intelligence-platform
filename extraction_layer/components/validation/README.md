# components/validation

`(ExtractionResult, TableExtractionResult)` → `ValidationResult` (list of rule findings).

## Technique

- **Format validators** — `invoice_no` digit count, `invoice_date` parseable, `tax_id` `XXX-XX-XXXX`, `iban` ISO prefix.
- **ISO 13616 mod-97 IBAN checksum** — detects ~96 % of transcription errors.
- **Item arithmetic** — `qty × net_price ≈ net_worth`; `net_worth × (1 + VAT/100) ≈ gross_worth`, with rounding tolerance `max(1.0, expected × 0.01)`.
- **Batch duplicate detection** — exact match on `(invoice_no, seller_tax_id, invoice_date)`.
- European decimal / percent parser handles `1 319,97` / `1319,97` / `1.319,97` interchangeably.

## Use case

- Decide whether an extracted-plus-tabled invoice is trustworthy to act on (flag for review, auto-export, etc.) — no ground truth required.

## Advantages

- GT-free — judges correctness intrinsically, not against a reference.
- < 1 ms / invoice.
- Rule outputs are `PASS / FAIL / NOT_APPLICABLE` with `expected` + `observed` values, so any finding is inspectable.
- Rules are independent functions — easy to add / disable.

## Disadvantages

- mod-97 doesn't catch *every* IBAN OCR error (~4 % pass coincidentally).
- Arithmetic tolerance is a heuristic; very small amounts need care.
- No GST / country-specific rules (PRD's Indian-phase work is deferred).

## Inputs / Outputs

- **Input**: combined `ExtractionResult` + `TableExtractionResult` (wrapped in a `ValidationInput` object). See `schema/input.example.json`.
- **Output**: `ValidationResult` — flat list of `RuleFinding` (`rule_name`, `target`, `outcome`, `reason`, `expected`, `observed`). See `schema/output.example.json`.
- Schemas regenerable via `python -m tools.regen_schemas`.

## Run standalone

```python
from components.validation import ValidationEngine

engine = ValidationEngine()
result = engine.validate(extraction_result, table_result)

print(result.summary())  # {'pass': N, 'fail': N, 'not_applicable': N}
for f in result.failures():
    print(f.rule_name, f.target, f.reason)
```

## Deploying as an independent service

Pure-Python rule engine — no heavy deps. Consumes
`ExtractionResult` + `TableExtractionResult` JSONs; emits a
`ValidationResult` JSON. The only component imports are the wire-format
types from extraction and tables — simple to vendor or serve as a
separate Lambda.
