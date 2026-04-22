# backend/

FastAPI app that wires the pipeline (OCR → extraction → tables → validation)
together and serves the HTML/JS viewer. Pipeline outputs are cached lazily
to JSONL per user direction (2026-04-19) — no warmup; each invoice pays
OCR cost once, on its first click.

## Layout

    backend/
    ├── app/
    │   ├── main.py          # FastAPI routes + static mount
    │   ├── pipeline.py      # PipelineRunner (OCR + extract + tables + validate)
    │   ├── cache.py         # PipelineCache — JSONL-backed, lazy
    │   └── csv_export.py    # Component M — invoice -> CSV bytes
    └── tests/
        ├── test_cache.py
        └── test_csv_export.py

The frontend is mounted at `/static` from `frontend/static/`.

## Run (PowerShell, from repo root)

    uv pip install -r requirements.txt
    uvicorn backend.app.main:app --reload --port 8000

Then open `http://localhost:8000/`.

First click on an invoice runs OCR + extraction + tables + validation
(~5–7 s on CPU). Subsequent clicks read from
`data/cache/pipeline_cache.jsonl` and are near-instant.

## Routes

| Route | Purpose |
|---|---|
| `GET /` | Serves the viewer HTML |
| `GET /static/...` | CSS / JS |
| `GET /api/invoices?split=test&limit=20` | Lightweight list — does not run the pipeline |
| `GET /api/invoices/{id}` | Full pipeline payload (cached after first call) |
| `GET /api/invoices/{id}/image.png` | Raw invoice image |
| `GET /api/invoices/{id}/export.csv` | Component M CSV (header + items) |
| `GET /api/invoices/{id}/cached` | `{"cached": bool}` — UI badge |
| `GET /api/meta` | Dataset + cache diagnostics |

## Cache

JSONL file at `data/cache/pipeline_cache.jsonl`. One record per line:

    {"id": "katanaml-test-00003", "data": {...}}

Corrupt lines are skipped (not fatal). Later records for the same `id`
supersede earlier ones. On restart the cache is re-read — no redo of
prior OCR work.

Delete the file to force a full re-run on next clicks:

    Remove-Item data\cache\pipeline_cache.jsonl

## Running tests

    pytest -m "not ocr_heavy and not dataset_heavy"

`test_cache.py` and `test_csv_export.py` are pure-Python (no OCR model, no
dataset) so they run in milliseconds.
