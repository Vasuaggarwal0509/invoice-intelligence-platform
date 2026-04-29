# Contributing

Day-to-day workflow + the conventions that keep `CHANGELOG.md` and
`DEPLOYMENTS.md` honest.

## Setup (once per machine)

```bash
git clone <repo-url>
cd invoice-intelligence-platform
make install              # builds venv, installs runtime + dev deps
pre-commit install        # registers .pre-commit-config.yaml hooks
```

You should now have `venv/bin/python` ready and `git commit` running ruff
automatically.

## Daily loop

```bash
make test                 # fast pytest (~22s)
make lint                 # ruff check + format check
make run                  # uvicorn with --reload on 0.0.0.0:8001
make smoke                # full end-to-end smoke (~10s)
make ci                   # exact sequence the GitHub workflow runs
```

## Conventional Commits

All commit messages must start with one of these prefixes. The CI
workflow doesn't enforce it (no commitlint configured) — but `CHANGELOG.md`
groups entries by these prefixes, so being consistent is what makes the
release notes write themselves later.

| Prefix      | When to use                                          | Example |
|-------------|-------------------------------------------------------|---------|
| `feat:`     | A new user-visible feature                            | `feat: CA dashboard derived-client list` |
| `fix:`      | A bug fix                                             | `fix: GSTIN regex was matching 16 chars` |
| `chore:`    | Build / tooling / infra plumbing — no behaviour change | `chore: add Dockerfile + render.yaml` |
| `docs:`     | Documentation only                                    | `docs: explain dummy.txt swap-in flow` |
| `refactor:` | Internal restructure, no observable change            | `refactor: extract gmail_source_service` |
| `test:`     | Adding / changing tests, no production code           | `test: cover CA → unrelated workspace 404` |
| `ci:`       | CI workflow / GitHub Actions config                   | `ci: cache pip on requirements-dev.txt hash` |
| `perf:`     | Performance improvement, behaviour unchanged          | `perf: index inbox_messages.received_at` |

Optional scope: `feat(ca): …`, `fix(oauth): …` — useful when the area is
clear and the message is otherwise short.

Optional `!` after the prefix marks a breaking change: `feat!: drop /api/v1`.

## Versioning

Single source of truth: the `version` field in `pyproject.toml`.

### When to bump

We're pre-1.0 (`0.x.y`), so:

- **Patch (0.0.1 → 0.0.2)**: bug fixes only, no new features.
- **Minor (0.0.1 → 0.1.0)**: new features, may include backwards-incompatible
  changes (this is fine pre-1.0).
- **Major**: hold until we serve a real user. The 1.0.0 bump signals
  "we promise to follow SemVer strictly from here".

### How to cut a release

```bash
# 1. Edit pyproject.toml — bump the version.
$EDITOR pyproject.toml

# 2. Update CHANGELOG.md — move [Unreleased] entries into a new
#    [X.Y.Z] section dated today.
$EDITOR CHANGELOG.md

# 3. Commit + tag.
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release v0.1.0"
git tag -a v0.1.0 -m "0.1.0 — features summary"
git push origin main --tags
```

`git push origin main --tags` triggers two things in parallel:
- GitHub Actions runs the CI workflow against the new commit.
- Render's auto-deploy picks up the push to `main` and rebuilds the
  Docker image.

After Render finishes:
- Append a row to `DEPLOYMENTS.md` with the live URL + SHA.

## Pre-commit hooks

The `.pre-commit-config.yaml` runs:

1. `ruff check --fix` (autofix lint issues)
2. `ruff format` (rewrites your file to canonical formatting)
3. The layer-import-graph pytest (catches `routes/` importing `db/`)
4. Trailing-whitespace + EOF newline + YAML/TOML syntax checks
5. Large-file blocker (>500 KB)

If a hook fails, your commit aborts. Fix the issue, `git add` the new
state, retry the commit. **Never use `git commit --no-verify`** — that
bypass loses the layer-rule check, which is the only thing standing
between us and a 30-min debug session of "why does routes/x.py import
repositories/y.py?".

## Branch model

- `main` — protected (in spirit); CI must be green before merge.
- `business`, `ca`, `email-sprint`, etc. — feature branches. Squash-merge
  into `main` so CHANGELOG entries map cleanly to single commits.
- `hotfix/*` — small fixes against `main` directly (still through a PR
  for the CI gate).

## Layer rules

The repository enforces these via the import-graph test:

```
business_layer/
├── app.py        ← may import routes, services
├── routes/       ← may import services, models
├── services/     ← may import repositories, models
├── repositories/ ← may import db, models
├── db/           ← may import models
└── models/       ← stdlib + pydantic only
```

Violations fail in CI before merge. If you genuinely need to break the
rule, a code review on the import-graph test change itself forces an
explicit conversation.
