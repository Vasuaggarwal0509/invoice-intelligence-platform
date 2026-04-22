"""
Regenerate per-component JSON schemas + example payloads.

Runs on demand (not in CI) to refresh the committed schema files under
``components/*/schema/`` whenever a wire-format Pydantic type changes.

Usage (PowerShell):

    python -m tools.regen_schemas

Each component publishes at most two schemas:
  * input.schema.json — the service-boundary input contract
  * output.schema.json — what the component emits

Alongside the schemas we write matching ``*.example.json`` files so a
consumer (future HTTP client, Lambda test event) has a paste-ready
payload. Examples are hand-curated here so they stay small and readable.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from extraction_layer.components.extraction.types import ExtractedField, ExtractionResult
from extraction_layer.components.ocr.types import (
    BoundingBox,
    InvoiceInput,
    Line,
    OCRResult,
    PageSize,
    Token,
)
from extraction_layer.components.tables.types import InvoiceItem, TableExtractionResult
from extraction_layer.components.validation.types import RuleFinding, RuleOutcome, ValidationResult


ROOT = Path(__file__).resolve().parent.parent


def _write_schema(component: str, name: str, model_cls) -> Path:
    """Write ``components/<component>/schema/<name>.schema.json`` from a Pydantic model."""
    out = ROOT / "components" / component / "schema" / f"{name}.schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = model_cls.model_json_schema()
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return out


def _write_example(component: str, name: str, payload: Any) -> Path:
    out = ROOT / "components" / component / "schema" / f"{name}.example.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


# --- OCR --------------------------------------------------------------------


def regen_ocr() -> list[Path]:
    paths: list[Path] = []
    paths.append(_write_schema("ocr", "input", InvoiceInput))
    paths.append(_write_schema("ocr", "output", OCRResult))

    # Example input — tiny 1x1 PNG (base64) so the example file is <100 bytes.
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01"
        b"\x5c\xcd\xffi\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    example_input = {
        "id": "sample-001",
        "content_type": "image/png",
        "image_bytes": base64.b64encode(tiny_png).decode("ascii"),
        "filename": "sample-001.png",
        "metadata": {"source": "example"},
    }
    paths.append(_write_example("ocr", "input", example_input))

    # Example output — one line, one token, matches real RapidOCR shape.
    example_output = OCRResult(
        tokens=[
            Token(
                text="INVOICE",
                bbox=BoundingBox(x0=100, y0=50, x1=220, y1=80),
                polygon=[[100, 50], [220, 50], [220, 80], [100, 80]],
                confidence=0.99,
            )
        ],
        lines=[
            Line(
                text="INVOICE 12345",
                bbox=BoundingBox(x0=100, y0=50, x1=360, y1=80),
                polygon=[[100, 50], [360, 50], [360, 80], [100, 80]],
                tokens=[
                    Token(
                        text="INVOICE",
                        bbox=BoundingBox(x0=100, y0=50, x1=220, y1=80),
                        polygon=[[100, 50], [220, 50], [220, 80], [100, 80]],
                        confidence=0.99,
                    ),
                    Token(
                        text="12345",
                        bbox=BoundingBox(x0=240, y0=50, x1=360, y1=80),
                        polygon=[[240, 50], [360, 50], [360, 80], [240, 80]],
                        confidence=0.97,
                    ),
                ],
                confidence=0.98,
            )
        ],
        page=PageSize(width=640, height=480),
        backend="rapidocr",
        duration_ms=187.4,
    )
    paths.append(_write_example("ocr", "output", example_output.model_dump()))
    return paths


# --- Extraction -------------------------------------------------------------


def regen_extraction() -> list[Path]:
    paths: list[Path] = []
    # Input = OCR output.
    paths.append(_write_schema("extraction", "input", OCRResult))
    paths.append(_write_schema("extraction", "output", ExtractionResult))

    # Example input — minimal OCR-shaped payload.
    example_input = OCRResult(
        tokens=[],
        lines=[
            Line(
                text="Invoice no: 12345",
                bbox=BoundingBox(x0=100, y0=50, x1=500, y1=80),
                confidence=0.99,
            ),
        ],
        page=PageSize(width=640, height=480),
        backend="rapidocr",
        duration_ms=187.4,
    )
    paths.append(_write_example("extraction", "input", example_input.model_dump()))

    # Example output — one extracted field.
    example_output = ExtractionResult(
        fields={
            "invoice_no": ExtractedField(
                name="invoice_no",
                value="12345",
                confidence=0.95,
                source="regex",
                source_detail="invoice_no anchor",
            ),
            "invoice_date": ExtractedField(
                name="invoice_date",
                value=None,
                confidence=0.0,
                source="none",
            ),
        },
        extractor="heuristic",
        duration_ms=0.6,
    )
    paths.append(_write_example("extraction", "output", example_output.model_dump()))
    return paths


# --- Tables -----------------------------------------------------------------


def regen_tables() -> list[Path]:
    paths: list[Path] = []
    # Input = OCR output.
    paths.append(_write_schema("tables", "input", OCRResult))
    paths.append(_write_schema("tables", "output", TableExtractionResult))

    example_input = OCRResult(
        tokens=[],
        lines=[
            Line(text="ITEMS", bbox=BoundingBox(x0=100, y0=500, x1=200, y1=525), confidence=0.99),
            Line(text="1.", bbox=BoundingBox(x0=120, y0=600, x1=145, y1=625), confidence=0.99),
            Line(text="Widget", bbox=BoundingBox(x0=180, y0=600, x1=300, y1=625), confidence=0.95),
            Line(text="2,00", bbox=BoundingBox(x0=350, y0=600, x1=400, y1=625), confidence=0.99),
            Line(text="each", bbox=BoundingBox(x0=430, y0=600, x1=470, y1=625), confidence=0.98),
            Line(text="50,00", bbox=BoundingBox(x0=500, y0=600, x1=570, y1=625), confidence=0.99),
            Line(text="100,00", bbox=BoundingBox(x0=600, y0=600, x1=670, y1=625), confidence=0.99),
            Line(text="10%", bbox=BoundingBox(x0=700, y0=600, x1=740, y1=625), confidence=0.99),
            Line(text="110,00", bbox=BoundingBox(x0=770, y0=600, x1=840, y1=625), confidence=0.99),
            Line(text="SUMMARY", bbox=BoundingBox(x0=100, y0=700, x1=200, y1=725), confidence=0.99),
        ],
        page=PageSize(width=900, height=1200),
        backend="rapidocr",
        duration_ms=200.0,
    )
    paths.append(_write_example("tables", "input", example_input.model_dump()))

    example_output = TableExtractionResult(
        items=[
            InvoiceItem(
                item_desc="Widget",
                item_qty="2,00",
                item_net_price="50,00",
                item_net_worth="100,00",
                item_vat="10%",
                item_gross_worth="110,00",
            )
        ],
        extractor="spatial",
        duration_ms=0.5,
        diagnostics={"anchor_count": 1},
    )
    paths.append(_write_example("tables", "output", example_output.model_dump()))
    return paths


# --- Validation -------------------------------------------------------------


def regen_validation() -> list[Path]:
    paths: list[Path] = []
    # Validation takes two inputs (extraction result + table result); the
    # input schema documents the compound shape as a wrapper object.
    from pydantic import BaseModel, Field

    class ValidationInput(BaseModel):
        """Compound input: an ExtractionResult + a TableExtractionResult."""
        extraction: ExtractionResult = Field(..., description="Header-field extraction result.")
        tables: TableExtractionResult = Field(..., description="Line-item extraction result.")

    paths.append(_write_schema("validation", "input", ValidationInput))
    paths.append(_write_schema("validation", "output", ValidationResult))

    example_input_obj = ValidationInput(
        extraction=ExtractionResult(
            fields={
                "invoice_no": ExtractedField(
                    name="invoice_no",
                    value="12345",
                    confidence=0.95,
                    source="regex",
                    source_detail="invoice_no anchor",
                ),
            },
            extractor="heuristic",
            duration_ms=0.6,
        ),
        tables=TableExtractionResult(
            items=[
                InvoiceItem(
                    item_desc="Widget",
                    item_qty="2,00",
                    item_net_price="50,00",
                    item_net_worth="100,00",
                    item_vat="10%",
                    item_gross_worth="110,00",
                )
            ],
            extractor="spatial",
            duration_ms=0.5,
        ),
    )
    paths.append(_write_example("validation", "input", example_input_obj.model_dump()))

    example_output = ValidationResult(
        findings=[
            RuleFinding(
                rule_name="invoice_no.format",
                target="invoice_no",
                outcome=RuleOutcome.PASS,
                reason="8 digits present",
            ),
            RuleFinding(
                rule_name="item.arithmetic",
                target="items[0]",
                outcome=RuleOutcome.PASS,
                reason="qty × net_price ≈ net_worth within tolerance",
                expected="100.00",
                observed="100.00",
            ),
        ],
        source="engine",
        metadata={"rule_count": 2},
    )
    paths.append(_write_example("validation", "output", example_output.model_dump()))
    return paths


# --- Orchestration ----------------------------------------------------------


def main() -> int:
    all_paths: list[Path] = []
    all_paths += regen_ocr()
    all_paths += regen_extraction()
    all_paths += regen_tables()
    all_paths += regen_validation()

    print(f"Wrote {len(all_paths)} files:")
    for p in all_paths:
        rel = p.relative_to(ROOT)
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
