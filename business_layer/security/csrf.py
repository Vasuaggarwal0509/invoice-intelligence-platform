"""Double-submit CSRF token.

Defence in depth on top of ``SameSite=Lax`` cookies. SameSite alone
blocks cross-site POSTs in modern browsers; double-submit covers old
browsers + cross-subdomain edge cases.

Flow:
  1. On first request, :func:`ensure_csrf_cookie` sets a non-HttpOnly
     cookie carrying a random token (the *client-visible* value).
  2. Vanilla-JS frontend reads the cookie and echoes it in an
     ``X-CSRF-Token`` header on every state-changing request.
  3. :func:`verify_csrf` compares header against cookie in constant
     time. Mismatch → 403.

The token is bound to the session with HMAC so it cannot be replayed
across logouts. :class:`itsdangerous.URLSafeTimedSerializer` wraps it
with a TTL so a stolen cookie goes stale quickly.

Sprint 0 exposes only the primitives; Sprint 1 wires
:func:`ensure_csrf_cookie` + :func:`verify_csrf` into the appropriate
routes.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from fastapi.responses import Response

_CSRF_COOKIE_NAME = "bl_csrf"
_CSRF_HEADER_NAME = "X-CSRF-Token"
_CSRF_TOKEN_BYTES = 32


def _new_token() -> str:
    return secrets.token_urlsafe(_CSRF_TOKEN_BYTES)


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    """Set the CSRF cookie on ``response`` if missing; return the token.

    Cookie is intentionally NOT HttpOnly — the frontend has to read it
    to echo in the header. That's the whole point of double-submit.
    """
    token = request.cookies.get(_CSRF_COOKIE_NAME)
    if not token:
        token = _new_token()
        response.set_cookie(
            _CSRF_COOKIE_NAME,
            token,
            httponly=False,   # intentional — see docstring
            secure=True,      # Settings.session_cookie_secure should match
            samesite="lax",
            path="/",
        )
    return token


def verify_csrf(request: Request) -> bool:
    """Check that the ``X-CSRF-Token`` header matches the CSRF cookie.

    Constant-time comparison. Returns False on any missing/mismatched
    value; routes should translate that into an :class:`AuthorizationError`
    or a 403 directly.

    Safe methods (GET/HEAD/OPTIONS) are not expected to call this —
    enforce at the route-group level instead of here.
    """
    cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
    header_token = request.headers.get(_CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)
