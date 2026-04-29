# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions live in `pyproject.toml` (`[project] version`). Release tags use
the form `vX.Y.Z`.

## [Unreleased]

Nothing yet — entries land here in chronological order, then move into a
versioned section at release time.

## [0.0.1] — 2026-04-30 (initial scaffold + CI/CD foundation)

### Added — Sprint 0 (auth + persistence)

- FastAPI app with structured logging, request_id correlation middleware,
  security headers, CSRF cookie middleware.
- SQLAlchemy 2.0 Core schema with auto-running migrations
  (`schema_migrations` tracker).
- Phone+OTP signup/login flow with rate limits, lockout counters,
  argon2-hashed sessions.
- Workspace-scoped data model + IDOR defences in every repository.
- 62 unit + integration + security tests.

### Added — Sprint 1 (security hardening)

- AES-GCM encryption helper (refresh tokens, OAuth state).
- `Settings` pydantic-settings module with env-var contract.
- Bandit + pip-audit + ruff + mypy in dev requirements.

### Added — Sprint 2 (extraction pipeline integration)

- Upload route with magic-byte content sniffing (python-magic).
- Background `extraction_worker` thread that drains a queue of pending
  invoices, calls the extraction_layer pipeline, stamps results.
- Inbox + invoice detail routes with persona-scoped views (business vs CA).

### Added — Sprint 3 (business dashboard)

- KPI tiles: invoices this month, total spend, ITC estimate, needs-review.
- Top-vendors-this-month aggregate.
- Needs-review list with click-through to invoice detail.

### Added — Sprint 4 (CA shell + derived-client list)

- CA persona signup/login (email + argon2 password, distinct from
  business phone+OTP flow).
- `workspaces.ca_gstin` linkage column (migration `0002_ca_linkage.sql`).
- Business → CA pairing endpoints (`POST/DELETE /api/business/ca-link`).
- CA dashboard routes (`/api/ca/clients`, per-client invoice list, CA-scoped
  invoice detail + image route).
- Persona chooser at `/`, distinct CA shell at `/ca` with teal accent.
- Cross-persona authorisation gates on every route.

### Added — Email ingestion sprint (Gmail OAuth)

- `services/oauth/google_oauth.py` — server-side OAuth 2.0 flow with
  itsdangerous-signed state + PKCE S256.
- `services/connectors/gmail_connector.py` — search Gmail with subject
  keywords from `config/config.json`, download attachments, hand to
  upload pipeline.
- `workers/gmail_poller.py` — threaded poll loop, only starts when a real
  OAuth client JSON is present.
- "Connect Email" button on business dashboard, dummy-config 502 graceful
  degrade, `dummy.txt` ledger documenting credential swap-in procedure.

### Added — CI/CD foundation (this version)

- GitHub Actions CI workflow (`.github/workflows/ci.yml`): lint + matrix
  pytest + smoke harness, runs on every PR + push to main.
- `Makefile` with the standard dev loop (`install`, `test`, `lint`, `run`,
  `smoke`, `build-image`, `version`, `clean`).
- `Dockerfile` (Python 3.12-slim, layered deps, non-root user, $PORT-aware).
- `.dockerignore` (excludes `data/`, `tests/`, `secrets/*` except
  `*_dummy.json`).
- `render.yaml` Blueprint for one-click deploy on Render.
- `tests/smoke/biz_layer_smoke.py` — 73-check end-to-end harness covering
  9 user-journey scenarios.
- `[tool.ruff]` + `[tool.mypy]` blocks in `pyproject.toml`.
- `requirements-dev.txt` with pinned versions of every CI tool.
- `.pre-commit-config.yaml` for local hooks.
- `business_layer/version_info.py` — single source of truth for version
  + git_sha, surfaced in startup log + `/health` body.
- Deep `/health` endpoint (returns version, git_sha, db check).
- 85/85 pytest + 73/73 smoke checks (158 independent test points).

[Unreleased]: https://github.com/Vasuaggarwal0509/invoice-intelligence-platform/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/Vasuaggarwal0509/invoice-intelligence-platform/releases/tag/v0.0.1
