"""Shared test fixtures for business_layer.

Provides:
  * An in-memory SQLite engine per test (no cross-test state).
  * A FastAPI ``TestClient`` wired to the fixture engine.
  * Safe defaults for required settings (PLATFORM_SECRET_KEY).
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

# Required by Settings at import time; set before any business_layer
# module is loaded.
os.environ.setdefault(
    "PLATFORM_SECRET_KEY",
    "test-secret-test-secret-test-secret-test-secret",
)
os.environ.setdefault("PLATFORM_ENV", "test")
os.environ.setdefault("PLATFORM_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("PLATFORM_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def test_client() -> Iterator[TestClient]:
    """Return a FastAPI TestClient with a fresh in-memory SQLite engine.

    Each test gets its own DB + rate-limit buckets + pipeline cache;
    teardown discards it automatically. Without per-test resets, the
    module-level singletons (rate_limit.limiter, extraction_runner
    pipeline cache) leak across tests and flake deterministic runs.
    """
    from business_layer.app import app_factory
    from business_layer.config import get_settings
    from business_layer.db import engine as db_engine
    from business_layer.security.rate_limit import limiter as _rate_limiter

    # Reset any cached state from previous tests.
    get_settings.cache_clear()
    db_engine._reset_for_tests()
    _rate_limiter.reset()
    # Clear the extraction pipeline cache so monkeypatched stubs take effect.
    import business_layer.services.extraction_runner as _er
    _er._pipeline_singleton = None

    application = app_factory()
    with TestClient(application) as client:
        yield client

    db_engine._reset_for_tests()
    get_settings.cache_clear()
    _rate_limiter.reset()
    _er._pipeline_singleton = None
