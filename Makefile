# Makefile — standard dev loop for the invoice-intelligence platform.
#
# Targets are POSIX-portable (Linux, macOS, WSL). The same commands run
# locally and in CI — no hidden divergence.
#
# Quick start (fresh clone):
#   make install         # build venv, install runtime + dev deps
#   make test            # fast pytest (no OCR/dataset-heavy tests)
#   make lint            # ruff check + format check
#   make run             # dev server with --reload on 0.0.0.0:8001
#
# CI parity:
#   make ci              # exactly what .github/workflows/ci.yml runs
#
# Container:
#   make build-image     # docker build, tagged with version from pyproject.toml

PYTHON := venv/bin/python
PIP    := venv/bin/pip
UVICORN := venv/bin/uvicorn

# Read the canonical version once. `make version` prints it.
VERSION := $(shell grep -E '^version' pyproject.toml | head -1 | cut -d'"' -f2)

.PHONY: install install-runtime test test-fast test-business test-extraction \
        lint format run smoke ci build-image clean version help

help:
	@echo "Common targets:"
	@echo "  make install         — fresh venv with dev tooling (pytest, ruff, mypy)"
	@echo "  make install-runtime — runtime only (matches Docker image install)"
	@echo "  make test            — pytest, fast path (skips ocr_heavy + dataset_heavy)"
	@echo "  make test-business   — only business_layer tests"
	@echo "  make lint            — ruff check + format check"
	@echo "  make format          — ruff format (rewrites files)"
	@echo "  make run             — uvicorn dev server, --host 0.0.0.0 --port 8001"
	@echo "  make smoke           — run the full end-to-end smoke harness"
	@echo "  make ci              — exact sequence the GitHub Actions workflow runs"
	@echo "  make build-image     — docker build, tagged $(VERSION) + latest"
	@echo "  make version         — print the canonical project version"
	@echo "  make clean           — remove caches + build artifacts"

install:
	python3 -m venv venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e .

install-runtime:
	python3 -m venv venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

test:
	$(PYTHON) -m pytest -m "not ocr_heavy and not dataset_heavy" -q

test-fast: test-business

test-business:
	$(PYTHON) -m pytest business_layer -q

test-extraction:
	$(PYTHON) -m pytest extraction_layer -m "not ocr_heavy and not dataset_heavy" -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

# --host 0.0.0.0 on purpose — under WSL+Windows, 127.0.0.1 bindings flake on
# Windows HNS port forwarding. 0.0.0.0 binds the WSL interface that the
# Windows browser actually reaches.
run:
	$(UVICORN) business_layer.app:app --reload --host 0.0.0.0 --port 8001

smoke:
	$(PYTHON) tests/smoke/biz_layer_smoke.py

# Exactly the CI sequence — useful for debugging a CI failure locally.
ci: lint test smoke

build-image:
	docker build -t invoice-intelligence:$(VERSION) -t invoice-intelligence:latest .

version:
	@echo $(VERSION)

clean:
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
