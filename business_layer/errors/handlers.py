"""FastAPI exception handlers — map domain + unknown errors to JSON responses.

Two handlers registered globally by :func:`register_exception_handlers`:

1. :class:`~business_layer.errors.PlatformError` → the class's declared
   ``status_code`` + a stable body ``{error, code, request_id, detail?}``.
2. :class:`Exception` (unknown) → 500 with body ``{error: "internal",
   code: "internal_error", request_id}``. Stack trace is logged; never
   returned.

Every response carries a ``request_id`` header the user can quote when
reporting a bug; on-call greps logs for the same value.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import ClientError, PlatformError, RateLimitedError, ServerError

_log = logging.getLogger(__name__)


def _new_request_id() -> str:
    """Return a short, opaque request id (UUID4 hex).

    Used as the correlation token between a response, an access log
    line, and whatever exception got logged along the way.
    """
    return uuid.uuid4().hex


def _safe_detail(exc: PlatformError) -> str:
    """Return a user-safe detail string.

    Client errors can show their detail; server errors never do (could
    leak stack frames, SQL state, etc. — we log them instead).
    """
    if isinstance(exc, ClientError):
        return exc.detail or exc.error_code
    return "The server encountered an error. Please retry; if it persists, quote the request_id."


async def _platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or _new_request_id()

    body: dict[str, Any] = {
        "error": exc.error_code,
        "code": exc.error_code,
        "request_id": request_id,
        "detail": _safe_detail(exc),
    }

    headers: dict[str, str] = {"X-Request-ID": request_id}
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after_seconds)

    # Log with full context server-side. Client errors → info; server errors → error.
    log_payload = {
        "request_id": request_id,
        "path": request.url.path,
        "method": request.method,
        "error_code": exc.error_code,
        "status": exc.status_code,
        "context": exc.context,
        "detail_internal": exc.detail,
    }
    if isinstance(exc, ServerError):
        _log.error("platform.server_error", extra=log_payload, exc_info=exc)
    else:
        _log.info("platform.client_error", extra=log_payload)

    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Normalise FastAPI/Pydantic request-validation errors to our envelope.

    FastAPI's default 422 body is ``{"detail": [<list of field errors>]}``,
    which breaks the frontend's ``api.js`` contract (``err.detail`` must be
    a string). We flatten to a single human-readable sentence per invalid
    field and return the same shape as every other ClientError.
    """
    request_id = getattr(request.state, "request_id", None) or _new_request_id()

    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(s) for s in err.get("loc", []) if s not in ("body", "query", "path"))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(parts) or "request body is invalid"

    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "code": "validation_failed",
            "request_id": request_id,
            "detail": detail,
        },
        headers={"X-Request-ID": request_id},
    )


async def _unknown_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for exceptions not subclassed from :class:`PlatformError`.

    These are code-level bugs. We log the whole stack trace but never
    show it to the caller — only a generic 500 body with request_id so
    the user can quote it in a support request.
    """
    request_id = getattr(request.state, "request_id", None) or _new_request_id()

    _log.exception(
        "platform.unhandled_exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "exc_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "code": "internal_error",
            "request_id": request_id,
            "detail": "The server encountered an error. Please retry; if it persists, quote the request_id.",
        },
        headers={"X-Request-ID": request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers above to a FastAPI app.

    Called once from :func:`business_layer.app.app_factory`. Order is
    specific → general: FastAPI dispatches to the most specific
    registered handler class, but explicit is cheaper than implicit.
    """
    app.add_exception_handler(PlatformError, _platform_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unknown_exception_handler)
