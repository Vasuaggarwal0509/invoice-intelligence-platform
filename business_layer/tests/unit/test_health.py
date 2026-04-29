"""Health endpoint smoke test — Sprint 0 gate."""

from __future__ import annotations


def test_health_returns_ok(test_client) -> None:  # type: ignore[no-untyped-def]
    """GET /health returns 200 with version + git_sha + db check when reachable."""
    response = test_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"db": "ok"}
    # Version comes from pyproject.toml — non-empty string, dotted SemVer.
    assert isinstance(body["version"], str) and body["version"]
    # git_sha is "dev" in tests (no RENDER_GIT_COMMIT or GIT_SHA env set).
    assert body["git_sha"] == "dev"


def test_health_sets_request_id_header(test_client) -> None:  # type: ignore[no-untyped-def]
    """Every response carries X-Request-ID for correlation."""
    response = test_client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_health_sets_security_headers(test_client) -> None:  # type: ignore[no-untyped-def]
    """Security middleware applies its header set on every response."""
    response = test_client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in response.headers.get("Content-Security-Policy", "")
