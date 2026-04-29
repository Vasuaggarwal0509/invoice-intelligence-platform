"""
FastAPI backend for the Invoice Intelligence PoC.

Routes:

    GET  /                              -> frontend index.html
    GET  /static/...                    -> static assets (CSS / JS)
    GET  /api/invoices                  -> list invoice IDs (with optional limit)
    GET  /api/invoices/{id}             -> full pipeline output (cached after first run)
    GET  /api/invoices/{id}/image.png   -> raw PNG image
    GET  /api/invoices/{id}/export.csv  -> CSV export for that invoice
    GET  /api/invoices/{id}/cached      -> small header telling the UI whether we'd hit cache

Caching: `PipelineCache` backed by a JSONL file. Nothing is pre-warmed;
a click on an uncached invoice is slow (OCR) once and fast thereafter.

Run (PowerShell):

    uvicorn backend.app.main:app --reload --port 8000
"""

import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from extraction_layer.components.extraction import ExtractionResult
from extraction_layer.components.tables import TableExtractionResult
from extraction_layer.data_sources import make_dataset
from extraction_layer.data_sources.katanaml_invoices import KatanamlInvoicesDataset

from .cache import PipelineCache
from .csv_export import invoice_to_csv
from .pipeline import PipelineRunner

# ----- paths + globals -------------------------------------------------------

_HERE = Path(__file__).resolve()
# _HERE = <repo_root>/extraction_layer/backend/app/main.py
EXTRACTION_LAYER_ROOT = _HERE.parent.parent.parent  # .../extraction_layer/
REPO_ROOT = EXTRACTION_LAYER_ROOT.parent  # .../
FRONTEND_DIR = EXTRACTION_LAYER_ROOT / "frontend" / "static"
# data/ stays at repo root (not under extraction_layer/) to keep HF's
# path-mangled lock filenames under Windows MAX_PATH=260.
CACHE_PATH = REPO_ROOT / "data" / "cache" / "pipeline_cache.jsonl"


# ----- app bootstrap ---------------------------------------------------------

app = FastAPI(title="Invoice Intelligence Platform", version="0.1.0")

dataset = make_dataset("katanaml")
pipeline = PipelineRunner()
cache = PipelineCache(CACHE_PATH)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ----- helpers ---------------------------------------------------------------


def _parse_invoice_id(invoice_id: str) -> tuple[str, int]:
    """IDs look like 'katanaml-test-00001' — return (split, index)."""
    parts = invoice_id.split("-")
    if len(parts) < 3 or parts[0] != "katanaml":
        raise HTTPException(status_code=400, detail=f"Bad invoice id: {invoice_id!r}")
    split = parts[1]
    try:
        index = int(parts[-1])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Bad index in {invoice_id!r}") from exc
    return split, index


def _sample_for(invoice_id: str):
    split, index = _parse_invoice_id(invoice_id)
    if split not in dataset.splits:
        raise HTTPException(status_code=404, detail=f"Unknown split {split!r}")
    if index < 0 or index >= dataset.count(split):
        raise HTTPException(
            status_code=404, detail=f"Index {index} out of range for split {split!r}"
        )
    return dataset.get(split, index)


def _run_and_cache(invoice_id: str) -> dict[str, Any]:
    """Run the pipeline, package the response payload, write to cache."""
    sample = _sample_for(invoice_id)
    ocr_result, extraction, tables, validation = pipeline.run(sample.image)

    payload: dict[str, Any] = {
        "id": invoice_id,
        "ocr": ocr_result.model_dump(mode="json"),
        "extraction": extraction.model_dump(mode="json"),
        "tables": tables.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json") if validation is not None else None,
        "ground_truth": {
            "header": KatanamlInvoicesDataset.header_of(sample),
            "items": KatanamlInvoicesDataset.items_of(sample),
        },
        "page": {
            "width": int(sample.image.shape[1]),
            "height": int(sample.image.shape[0]),
        },
    }
    cache.put(invoice_id, payload)
    return payload


def _extraction_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult.model_validate(payload["extraction"])


def _tables_from_payload(payload: dict[str, Any]) -> TableExtractionResult:
    return TableExtractionResult.model_validate(payload["tables"])


# ----- routes ----------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> Any:
    """Serve the HTML viewer."""
    index_html = FRONTEND_DIR / "index.html"
    if not index_html.exists():
        return PlainTextResponse(
            "Frontend not built. Expected at " + str(index_html),
            status_code=503,
        )
    return FileResponse(index_html)


@app.get("/api/invoices")
def list_invoices(
    split: str = Query(default="test"),
    limit: int = Query(default=20, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List invoice headers (lightweight — does not run the pipeline)."""
    if split not in dataset.splits:
        raise HTTPException(status_code=404, detail=f"Unknown split {split!r}")
    total = min(limit, dataset.count(split))
    items: list[dict[str, Any]] = []
    for i in range(total):
        sample = dataset.get(split, i)
        header = KatanamlInvoicesDataset.header_of(sample)
        items.append(
            {
                "id": sample.id,
                "split": split,
                "index": i,
                "invoice_no": header.get("invoice_no"),
                "invoice_date": header.get("invoice_date"),
                "cached": cache.contains(sample.id),
            }
        )
    return items


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: str) -> dict[str, Any]:
    """Return cached pipeline output, or run the pipeline first then cache."""
    cached = cache.get(invoice_id)
    if cached is not None:
        return cached
    return _run_and_cache(invoice_id)


@app.get("/api/invoices/{invoice_id}/image.png")
def get_invoice_image(invoice_id: str) -> Response:
    """Serve the invoice image as PNG."""
    sample = _sample_for(invoice_id)
    buf = io.BytesIO()
    Image.fromarray(sample.image).save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/invoices/{invoice_id}/export.csv")
def get_invoice_csv(invoice_id: str) -> Response:
    """CSV export (header fields + one row per line item)."""
    payload = cache.get(invoice_id) or _run_and_cache(invoice_id)
    extraction = _extraction_from_payload(payload)
    tables = _tables_from_payload(payload)
    csv_text = invoice_to_csv(extraction, tables)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{invoice_id}.csv"'},
    )


@app.get("/api/invoices/{invoice_id}/cached")
def get_cached_flag(invoice_id: str) -> dict[str, bool]:
    return {"cached": cache.contains(invoice_id)}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Small metadata endpoint for the UI."""
    return {
        "dataset": dataset.name,
        "splits": dataset.splits,
        "counts": {s: dataset.count(s) for s in dataset.splits},
        "cache_path": str(CACHE_PATH),
        "cached_count": len(cache.keys()),
    }


@app.on_event("startup")
def _startup() -> None:  # pragma: no cover - runtime only
    # OCR models load on first request naturally; we do **not** warm up
    # here because the user explicitly wanted per-click latency, not a
    # slow boot.
    # Load the cache index so `cached` flags work on the first /api/invoices call.
    _ = cache.keys()
