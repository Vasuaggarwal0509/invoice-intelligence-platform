"""Middleware that ensures the double-submit CSRF cookie is set on every response.

First page load sees no cookie → middleware generates one → subsequent
requests carry it, and the frontend echoes it in ``X-CSRF-Token`` for
state-changing calls.

Non-HttpOnly by design (the JS has to read it). Matches the cookie
name and attributes used by :mod:`business_layer.security.csrf`.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from business_layer.config import Settings

_CSRF_COOKIE_NAME = "bl_csrf"
_CSRF_TOKEN_BYTES = 32


class CsrfCookieMiddleware(BaseHTTPMiddleware):
    """Set the CSRF cookie on any response that doesn't already have the cookie on the request.

    The cookie value is random 32 bytes of urlsafe base64 — same
    entropy class as the session token. Vanilla-JS frontend reads it
    via ``document.cookie`` and echoes in an ``X-CSRF-Token`` header.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._cookie_secure = settings.session_cookie_secure

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        if _CSRF_COOKIE_NAME not in request.cookies:
            response.set_cookie(
                _CSRF_COOKIE_NAME,
                secrets.token_urlsafe(_CSRF_TOKEN_BYTES),
                httponly=False,  # intentional — JS must read it
                secure=self._cookie_secure,
                samesite="lax",
                path="/",
            )
        return response
