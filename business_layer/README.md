# business_layer

Onboarding platform with two independent personas (CA-firm + Business-enterprise), unified ingestion inbox, and persona-tuned dashboards.

**Sprint 0 not yet shipped.** This folder is scaffolded but empty pending the first sprint of implementation work.

## Design reference

See `docs/business_plan.md` for the full design: personas, dashboard content specs, unified inbox, UI patterns, onboarding flow, view architecture, data model, journey maps, delivery slices.

## Planned layout (Sprint 0 will populate)

```
business_layer/
├── config/           # Pydantic-Settings
├── db/               # SQLAlchemy 2.0 + SQLite schema
├── models/           # Pydantic request/response DTOs
├── errors/           # PlatformError hierarchy + FastAPI handlers
├── security/         # auth, sessions, OTP, encryption, rate limit, headers
├── repositories/     # data access
├── services/         # business logic
├── workers/          # in-process extraction worker thread
├── routes/           # FastAPI routes
├── static/           # vanilla HTML + JS per persona (business/, ca/)
└── tests/
```
