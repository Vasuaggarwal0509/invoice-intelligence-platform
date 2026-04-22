# extraction_layer

The PoC pipeline — **OCR → entity extraction → table extraction → validation** — plus the FastAPI invoice viewer. All baseline-gated and frozen-contract per `docs/project.md` §1.

## Layout

- `components/` — four pipeline stages, each independently deployable (own `types.py`, `base.py`, factory, schemas)
- `data_sources/` — HuggingFace-backed dataset loaders (Katanaml primary, SROIE / MIDD scaffolded)
- `backend/` — FastAPI app that stitches the components + serves the viewer
- `frontend/` — vanilla HTML/CSS/JS viewer (no framework, no build step)
- `evaluation/` — dated reports from gate runs
- `tools/` — CLIs (`regen_schemas`, `evaluate`, `download_dataset`)
- `data/` — gitignored; HF cache + pipeline JSONL cache live here

## Quick-start (from repo root)

```bash
source venv/bin/activate
uvicorn extraction_layer.backend.app.main:app --reload --port 8000
```

## Tests

```bash
pytest -m "not ocr_heavy and not dataset_heavy" extraction_layer/
```

Full architecture story, tech choices, and build order live in `docs/project.md`.
