"""Security-header middleware.

Sets a conservative default set of headers on every response:

* ``Strict-Transport-Security`` — only when :attr:`Settings.hsts_enabled`
  is true (prod). Dev uses plain HTTP over localhost and must not get
  HSTS pinned into a browser.
* ``Content-Security-Policy`` — strictest form: only self-hosted JS/CSS,
  no inline, no eval. All dynamic content goes through ``textContent``
  in the frontend (see ``business_layer/static/*/js/``).
* ``X-Content-Type-Options: nosniff`` — browsers must trust our
  ``Content-Type`` header.
* ``X-Frame-Options: DENY`` — prevents clickjacking by iframe.
* ``Referrer-Policy`` — minimise referrer leakage to third parties.
* ``Permissions-Policy`` — deny camera/microphone/geolocation access.

These are applied as middleware so they cover *every* response, including
error responses produced by :mod:`business_layer.errors.handlers`.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from business_layer.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-oriented headers to every response.

    Kept as a class (rather than a function middleware) so per-instance
    config (e.g. whether HSTS is on) is bound cleanly at startup rather
    than re-read every request.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts_enabled = settings.hsts_enabled

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        # Core hardening, unconditional.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        )

        # CSP — strictest form; no inline script, no inline style.
        # `img-src 'self' data:` lets base64-encoded thumbnails render
        # without hitting the network.
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "font-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
        )

        if self._hsts_enabled:
            # Only enable in prod over HTTPS. `preload` omitted until we
            # explicitly apply to the HSTS preload list.
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
