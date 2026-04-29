# Invoice Intelligence Platform

[![CI](https://github.com/Vasuaggarwal0509/invoice-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Vasuaggarwal0509/invoice-intelligence-platform/actions/workflows/ci.yml)

A two-layer platform for Indian GST invoice ingestion, extraction, validation, and onboarding.

## Layout

- **`extraction_layer/`** — the PoC pipeline (OCR → entity extraction → table extraction → validation) + FastAPI viewer. See `extraction_layer/README.md`.
- **`business_layer/`** — multi-tenant onboarding platform with business and CA persona dashboards, OAuth-based Gmail ingestion. See `business_layer/README.md` and `docs/business_plan.md`.
- **`docs/`** — project documentation (`project.md`, `business_plan.md`, `progress.md`, `contributing.md`, PRD). See `docs/README.md`.
- **`config/config.json`** — operator-tunable runtime config (email-ingestion keywords, file types, limits). Edit, restart, takes effect.
- **`secrets/`** — gitignored. Real OAuth client JSONs go here. `*_dummy.json` placeholders are committed; see `dummy.txt` for the swap-in procedure.

## Quick start

```bash
git clone <this-repo>
cd invoice-intelligence-platform

# One command builds the venv + installs runtime + dev tooling.
make install

# Run the business layer (port 8001) — landing page → persona chooser.
make run
```

Open <http://localhost:8001/>.

For the standalone extraction viewer:

```bash
source venv/bin/activate
uvicorn extraction_layer.backend.app.main:app --reload --port 8000
```

## Development

Standard targets in the [`Makefile`](Makefile):

| Command            | What it does |
|--------------------|--------------|
| `make install`     | Fresh venv + runtime + dev deps |
| `make test`        | Fast pytest (skips `ocr_heavy` + `dataset_heavy`) — ~22 s |
| `make test-fast`   | business_layer tests only — ~7 s |
| `make lint`        | ruff check + format check |
| `make format`      | ruff format (rewrites files) |
| `make run`         | uvicorn dev server on `0.0.0.0:8001` |
| `make smoke`       | End-to-end smoke harness — 73 checks across 9 user journeys |
| `make ci`          | Exact sequence the GitHub Actions workflow runs |
| `make build-image` | Build the Docker image, tagged with the version from `pyproject.toml` |
| `make version`     | Print the canonical project version |
| `make clean`       | Remove caches + build artifacts |

CI gate runs on every PR and push to `main`/`business`. See `.github/workflows/ci.yml`.

## Conventions

- **Commits**: [Conventional Commits](docs/contributing.md#conventional-commits) (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).
- **Versioning**: SemVer in `pyproject.toml`. Tag releases as `vX.Y.Z`. See `CHANGELOG.md`.
- **Layer rules**: enforced by the import-graph test —
  `routes → services → repositories → db → models`. No hopping levels.

## Deployment

Production target: **Render** (free tier). Connect this repo on
<https://render.com> → "New Blueprint Instance" → Render reads
[`render.yaml`](render.yaml) and builds the [`Dockerfile`](Dockerfile).

Auto-deploy on push to `main` is enabled. Track each rollout in
[`DEPLOYMENTS.md`](DEPLOYMENTS.md).

Real Gmail OAuth credentials are documented in [`dummy.txt`](dummy.txt) — the
codebase ships with `secrets/google_oauth_client_dummy.json` so a fresh clone
boots cleanly; replace with the real client JSON before connecting Gmail.

## Test counts

| Layer | Tests |
|---|---|
| `business_layer` | 85 (unit + integration + security) |
| `extraction_layer` | 387 fast + ocr_heavy + dataset_heavy markers |
| End-to-end smoke | 73 checks across 9 user journeys |
| **Combined safety net** | **~545 independent test points** |

## License

TBD — internal college project for now.
