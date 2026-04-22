# Invoice Intelligence Platform

A two-layer platform for Indian GST invoice ingestion, extraction, validation, and onboarding.

## Layout

- **`extraction_layer/`** — the PoC pipeline (OCR → entity extraction → table extraction → validation) + FastAPI viewer. Baseline-gated and frozen-contract. See `extraction_layer/README.md`.
- **`business_layer/`** — onboarding platform with CA and Business-owner dashboards (Sprint 0 not yet shipped). See `docs/business_plan.md` for the design and `business_layer/README.md` for Sprint status.
- **`docs/`** — project-level documentation (`project.md`, `business_plan.md`, `progress.md`, `research.md`, `learning.md`, PRD). See `docs/README.md`.

## Setup (one-time, from repo root)

```bash
python -m venv venv
source venv/bin/activate          # .\venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
pip install -e .
```

Root venv is the single venv. Both layers are installed as editable packages.

## Run the extraction viewer

```bash
source venv/bin/activate
uvicorn extraction_layer.backend.app.main:app --reload --port 8000
```

Open `http://localhost:8000/` and select a test invoice.

## Run tests

```bash
pytest -m "not ocr_heavy and not dataset_heavy"
```

387 fast tests. `ocr_heavy` + `dataset_heavy` markers are deselected by default; include them when you explicitly want to exercise OCR models or enumerate real datasets.
