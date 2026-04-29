"""FastAPI :class:`Depends` factories.

Every route that needs "the current user" or "the current workspace"
depends on a function here. That centralises auth resolution + gives
tests one place to override.

Rules of thumb:
* Routes call services, never repositories directly — so deps only
  expose what services return.
* Deps never touch FastAPI internals of the request beyond reading
  cookies / headers / client.host. They delegate everything else.
* The CSRF dependency here is *explicit*: routes opt in. We don't
  force it on authentication endpoints where the user hasn't yet
  visited the site (OTP request is allowed without CSRF since the
  cookie setter middleware might not have run yet).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from business_layer.config import Settings, get_settings
from business_layer.db import get_session
from business_layer.errors import AuthorizationError
from business_layer.security.csrf import verify_csrf
from business_layer.services import UserRow, WorkspaceRow
from business_layer.services.auth_service import resolve_session


def session_dep() -> Iterator[Session]:
    """Yield a SQLAlchemy session for one request lifecycle.

    Thin wrapper around :func:`business_layer.db.get_session` so routes
    use the FastAPI ``Depends()`` pattern consistently.
    """
    with get_session() as session:
        yield session


def settings_dep() -> Settings:
    """Return the singleton :class:`Settings`."""
    return get_settings()


def client_ip_dep(request: Request) -> str:
    """Best-effort client IP.

    ``X-Forwarded-For`` if set by a reverse proxy, else ``client.host``.
    Used only for rate-limit bucket keys + session audit rows — never
    for authorization.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First hop is the original client; rest is proxy chain.
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def user_agent_dep(request: Request) -> str | None:
    return request.headers.get("User-Agent")


def current_session_token_dep(
    request: Request,
    settings: Settings = Depends(settings_dep),
) -> str:
    """Read the session cookie; empty string if absent.

    Non-raising — the service decides whether the route needs auth.
    """
    return request.cookies.get(settings.session_cookie_name, "") or ""


def current_context_dep(
    token: str = Depends(current_session_token_dep),
    session: Session = Depends(session_dep),
) -> tuple[UserRow, WorkspaceRow]:
    """Resolve (user, workspace) from the cookie, or raise 401.

    Every authenticated route depends on this.
    """
    resolved = resolve_session(session, token_plaintext=token)
    return resolved.user, resolved.workspace


def require_csrf_dep(request: Request) -> None:
    """Raise 403 if the request fails the double-submit check.

    Add via ``dependencies=[Depends(require_csrf_dep)]`` on any
    state-changing route that runs with an authenticated session.
    """
    if not verify_csrf(request):
        raise AuthorizationError("csrf token missing or invalid")
