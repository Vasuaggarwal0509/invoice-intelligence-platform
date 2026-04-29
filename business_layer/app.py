"""FastAPI app composition — the bootstrap module.

Run with:

    uvicorn business_layer.app:app --reload --port 8001

Responsibilities:
  1. Construct the :class:`FastAPI` instance.
  2. Mount middleware stack (security headers + request_id stamping).
  3. Register exception handlers.
  4. Mount static assets (per-persona bundles arrive in Sprint 1+).
  5. Include routers.
  6. Apply database migrations on startup.

Nothing else — business logic lives in services, not here. Keeping this
module small means reviewers can see the whole request lifecycle at a
glance.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from business_layer.config import Settings, get_settings
from business_layer.db import init_db
from business_layer.errors import register_exception_handlers
from business_layer.routes import auth as auth_routes
from business_layer.routes import business as business_routes
from business_layer.routes import ca as ca_routes
from business_layer.routes import ca_auth as ca_auth_routes
from business_layer.routes import health as health_routes
from business_layer.routes import inbox as inbox_routes
from business_layer.routes import invoices as invoice_routes
from business_layer.routes import oauth as oauth_routes
from business_layer.routes import sources as source_routes
from business_layer.routes import upload as upload_routes
from business_layer.security.csrf_middleware import CsrfCookieMiddleware
from business_layer.security.headers import SecurityHeadersMiddleware
from business_layer.services.oauth import google_oauth
from business_layer.workers.extraction_worker import worker as extraction_worker
from business_layer.workers.gmail_poller import poller as gmail_poller

_log = logging.getLogger(__name__)

# Static assets live under business_layer/static/; per-persona subdirs
# (business/, ca/) are populated by later sprints.
_STATIC_DIR = Path(__file__).resolve().parent / "static"


class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a ``request_id`` and echo it in the response.

    The id is exposed at ``request.state.request_id`` so exception
    handlers + route code + log lines correlate against the same
    value. Header name ``X-Request-ID`` lets clients supply their own
    id (honoured if present, generated if not).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        return response


def _configure_logging(settings: Settings) -> None:
    """Baseline logging config.

    Full structlog JSON formatting is wired later — Sprint 0 uses
    stdlib logging with a simple format so tests don't depend on
    structlog for import.
    """
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def app_factory() -> FastAPI:
    """Build and return a configured FastAPI instance.

    Exposed as a function (not a module-level app) so tests can
    construct an isolated app per test if needed. The module-level
    :data:`app` below calls this once at import time for the uvicorn
    entrypoint.
    """
    settings = get_settings()
    _configure_logging(settings)

    fastapi_app = FastAPI(
        title=settings.app_name,
        version="0.0.1",
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )

    # Middleware order (Starlette applies in REVERSE of add order — the
    # last add_middleware call runs first on the way in).
    #   request-id (outermost) → security-headers → csrf-cookie → app
    # Rationale:
    #   * request-id must be set before anything else logs.
    #   * security headers wrap every response including error paths.
    #   * csrf-cookie runs inside them so it only fires on successful
    #     dispatches (setting the cookie on a crashed response is fine
    #     either way, but ordering is deterministic).
    fastapi_app.add_middleware(CsrfCookieMiddleware, settings=settings)
    fastapi_app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    fastapi_app.add_middleware(_RequestIDMiddleware)

    register_exception_handlers(fastapi_app)

    # Static assets — served under /static. Harmless if the dirs are
    # empty; populated by later sprints.
    if _STATIC_DIR.exists():
        fastapi_app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # Landing page (persona chooser). Authenticated users skip to their
    # persona shell via the JS in the landing page itself.
    @fastapi_app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/static/landing/index.html")

    # Direct shell entry points — handy for bookmarking + for
    # redirects from OAuth callbacks that know which persona they
    # belong to.
    @fastapi_app.get("/business", include_in_schema=False)
    def _business_redirect() -> RedirectResponse:
        return RedirectResponse(url="/static/business/index.html")

    @fastapi_app.get("/ca", include_in_schema=False)
    def _ca_redirect() -> RedirectResponse:
        return RedirectResponse(url="/static/ca/index.html")

    # Browsers auto-request /favicon.ico; no-op 204 keeps the access log clean.
    # Real favicon arrives whenever branding does — out of scope for Sprint 2.
    @fastapi_app.get("/favicon.ico", include_in_schema=False)
    def _favicon() -> Response:
        return Response(status_code=204)

    # Routers.
    fastapi_app.include_router(health_routes.router)
    fastapi_app.include_router(auth_routes.router)
    fastapi_app.include_router(upload_routes.router)
    fastapi_app.include_router(inbox_routes.router)
    fastapi_app.include_router(invoice_routes.router)
    fastapi_app.include_router(source_routes.router)
    fastapi_app.include_router(business_routes.router)
    fastapi_app.include_router(ca_auth_routes.router)
    fastapi_app.include_router(ca_routes.router)
    fastapi_app.include_router(oauth_routes.router)

    # Migrations — run on startup. Idempotent, so reload-restart is safe.
    # The extraction worker spins up in the same hook so it's ready to
    # pick jobs the moment the app serves its first upload.
    @fastapi_app.on_event("startup")
    def _startup() -> None:  # pragma: no cover - exercised by integration tests
        init_db()
        # Tests bypass the thread (see conftest "no_background_worker"
        # fixture); production and dev use the live thread.
        if settings.env != "test":
            extraction_worker.start()
            # Only start the gmail poller if a real OAuth client is
            # configured — otherwise it'd spin uselessly every tick.
            if google_oauth.is_configured():
                gmail_poller.start()
            else:
                _log.info(
                    "app.startup.gmail_poller_skipped",
                    extra={"reason": "oauth_client_not_configured"},
                )
        from business_layer.version_info import get_git_sha, get_version

        _log.info(
            "app.startup.complete",
            extra={
                "env": settings.env,
                "version": get_version(),
                "git_sha": get_git_sha(),
            },
        )

    @fastapi_app.on_event("shutdown")
    def _shutdown() -> None:  # pragma: no cover
        extraction_worker.stop()
        gmail_poller.stop()

    return fastapi_app


# Module-level singleton for uvicorn / gunicorn entrypoints.
app = app_factory()
