"""Exception hierarchy + handler contract tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from business_layer.errors import (
    AuthenticationError,
    BusinessRuleError,
    ClientError,
    ConflictError,
    DependencyError,
    InternalError,
    NotFoundError,
    PlatformError,
    RateLimitedError,
    ServerError,
    register_exception_handlers,
)


class TestHierarchy:
    def test_client_subclasses(self) -> None:
        for cls in (
            AuthenticationError,
            NotFoundError,
            ConflictError,
            BusinessRuleError,
            RateLimitedError,
        ):
            assert issubclass(cls, ClientError)
            assert issubclass(cls, PlatformError)

    def test_server_subclasses(self) -> None:
        for cls in (DependencyError, InternalError):
            assert issubclass(cls, ServerError)
            assert issubclass(cls, PlatformError)

    def test_rate_limited_carries_retry_after(self) -> None:
        err = RateLimitedError("slow down", retry_after_seconds=60)
        assert err.retry_after_seconds == 60


def _mini_app_with_route(exc: Exception) -> FastAPI:
    """Build a minimal FastAPI app that raises ``exc`` from one route."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


class TestHandlerMapping:
    def test_client_error_returns_status_and_safe_detail(self) -> None:
        app = _mini_app_with_route(NotFoundError("workspace not found"))
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert body["detail"] == "workspace not found"
        assert body["request_id"]

    def test_server_error_hides_detail(self) -> None:
        app = _mini_app_with_route(DependencyError("OCR backend crashed: <stack>"))
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 502
        body = resp.json()
        # Detail is generic; real detail is logged, not returned.
        assert "OCR" not in body["detail"]
        assert body["code"] == "dependency_error"

    def test_unknown_exception_becomes_500(self) -> None:
        app = _mini_app_with_route(RuntimeError("unexpected"))
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "internal_error"
        assert "unexpected" not in body["detail"]

    def test_rate_limited_sets_retry_after_header(self) -> None:
        app = _mini_app_with_route(RateLimitedError("slow", retry_after_seconds=42))
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "42"
