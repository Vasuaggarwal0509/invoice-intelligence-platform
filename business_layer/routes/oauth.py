"""Google OAuth 2.0 routes — start consent + handle callback + disconnect.

Flow:
  GET  /api/oauth/google/start      → 302 to Google consent
  GET  /api/oauth/google/callback   → exchange code, persist token,
                                      redirect back to dashboard
  POST /api/oauth/google/disconnect → wipe stored refresh token

Business-role only. CAs see their clients' invoices via the derived
list — no direct Gmail connection on their side.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from business_layer.errors import AuthorizationError, DependencyError
from business_layer.services import UserRow, WorkspaceRow, gmail_source_service
from business_layer.services.oauth import google_oauth

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/oauth/google", tags=["oauth"])

_log = logging.getLogger(__name__)


def _require_business(user: UserRow) -> None:
    if user.role != "business":
        raise AuthorizationError("gmail connection is for business accounts only")


@router.get("/start")
def get_start(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
) -> RedirectResponse:
    """Kick off the Google OAuth flow.

    If the OAuth client file is still the dummy placeholder we 503
    rather than sending the user through a broken consent screen.
    """
    user, workspace = ctx
    _require_business(user)
    if not google_oauth.is_configured():
        raise DependencyError(
            "gmail integration is not configured on this server yet",
        )
    bundle = google_oauth.build_auth_url(user_id=user.id, workspace_id=workspace.id)
    _log.info(
        "oauth.google.start",
        extra={"user_id": user.id, "workspace_id": workspace.id},
    )
    return RedirectResponse(url=bundle.auth_url, status_code=302)


@router.get("/callback")
def get_callback(
    request: Request,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> RedirectResponse:
    """Google redirects here. We verify state, exchange code, persist token."""
    user, workspace = ctx
    _require_business(user)

    query = request.query_params
    code = query.get("code")
    state = query.get("state")
    error = query.get("error")

    if error:
        _log.info("oauth.google.user_denied", extra={"error": error})
        return RedirectResponse(url="/business#/dashboard?gmail=denied", status_code=302)

    if not code or not state:
        raise AuthorizationError("missing code or state")

    decoded = google_oauth.decode_state(state)
    if decoded.user_id != user.id or decoded.workspace_id != workspace.id:
        # Someone replayed a state in a different session.
        raise AuthorizationError("oauth state does not match session")

    tokens = google_oauth.exchange_code(code=code, code_verifier=decoded.code_verifier)
    encrypted = google_oauth.encrypt_refresh_token(
        refresh_token=tokens.refresh_token,
        workspace_id=workspace.id,
    )
    gmail_source_service.upsert_connection(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        encrypted_refresh_token=encrypted,
    )
    _log.info("oauth.google.connected", extra={"workspace_id": workspace.id})
    return RedirectResponse(url="/business#/dashboard?gmail=connected", status_code=302)


@router.post("/disconnect")
def post_disconnect(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> dict[str, Any]:
    """Mark the workspace's Gmail source disconnected + wipe stored token."""
    user, workspace = ctx
    _require_business(user)
    status = gmail_source_service.disconnect(session, workspace_id=workspace.id, user_id=user.id)
    return {"status": status}
