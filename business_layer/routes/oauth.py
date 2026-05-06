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

from business_layer.errors import AuthenticationError, AuthorizationError, DependencyError
from business_layer.services import UserRow, WorkspaceRow, gmail_source_service
from business_layer.services.auth_service import issue_session, resolve_session
from business_layer.services.oauth import google_oauth

from .deps import client_ip_dep, current_context_dep, session_dep, settings_dep, user_agent_dep

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
    session=Depends(session_dep),
    settings=Depends(settings_dep),
    client_ip: str = Depends(client_ip_dep),
    user_agent: str | None = Depends(user_agent_dep),
) -> RedirectResponse:
    """Google redirects here. Verify state, exchange code, persist token.

    Authentication model: we DON'T require a session cookie at this
    point — instead we trust the signed ``state`` token Google echoed
    back. The state is:
      * HMAC-signed with our master secret (only our server can mint
        or verify it)
      * Time-limited to 10 minutes
      * Generated only by ``/api/oauth/google/start``, which itself
        requires an authenticated business-role session

    So a valid state proves the user authorized this OAuth flow while
    legitimately signed in. The Google ``code`` proves they completed
    consent at Google for the same flow (state was sent to Google in
    step 1 and Google echoes it back). Together that's stronger than
    a cookie cross-check.

    Why we relaxed the cookie requirement: browsers occasionally drop
    SameSite=Lax cookies on the redirect-back from Google (depends on
    how the redirect chain interacts with the user's privacy
    settings). When that happens with the strict cross-check, the
    user fails the OAuth flow even though everything else worked.
    Trusting the state means the flow completes regardless.

    Defence-in-depth: if the cookie IS sent, we still cross-check it
    matches the state's user_id. Mismatch → state was replayed by a
    different account; refuse.
    """
    query = request.query_params
    code = query.get("code")
    state = query.get("state")
    error = query.get("error")

    if error:
        _log.info("oauth.google.user_denied", extra={"error": error})
        return RedirectResponse(url="/business#/dashboard?gmail=denied", status_code=302)

    if not code or not state:
        raise AuthorizationError("missing code or state")

    # Verify + decode the signed state. If decoding fails (bad
    # signature, expired) the helper raises AuthorizationError → 403.
    decoded = google_oauth.decode_state(state)

    # Defence-in-depth: if a session cookie was sent, cross-check.
    # We deliberately swallow expired/invalid-token errors here —
    # falling through to state-only auth is the whole point of this
    # design. A WRONG-user cookie still blocks (replay protection).
    has_valid_session = False
    token = request.cookies.get(settings.session_cookie_name, "")
    if token:
        try:
            resolved = resolve_session(session, token_plaintext=token)
            if resolved.user.id != decoded.user_id:
                raise AuthorizationError("oauth state does not match session")
            has_valid_session = True
        except AuthenticationError:
            # Cookie expired / invalid / not in DB. Trust the state alone.
            pass

    tokens = google_oauth.exchange_code(code=code, code_verifier=decoded.code_verifier)
    encrypted = google_oauth.encrypt_refresh_token(
        refresh_token=tokens.refresh_token,
        workspace_id=decoded.workspace_id,
    )
    gmail_source_service.upsert_connection(
        session,
        workspace_id=decoded.workspace_id,
        user_id=decoded.user_id,
        encrypted_refresh_token=encrypted,
        email_address=tokens.email_address,
    )
    _log.info(
        "oauth.google.connected",
        extra={"workspace_id": decoded.workspace_id, "user_id": decoded.user_id},
    )

    redirect = RedirectResponse(url="/business#/dashboard?gmail=connected", status_code=302)

    # Session-revival: if the cookie was lost (browser dropped it on
    # the cross-site redirect from Google, OR it expired), mint a
    # fresh one for the user encoded in the signed state. Without
    # this, the user lands on /dashboard with no auth → bounces to
    # /login → has to re-OTP just to see the result of the OAuth
    # flow they just completed. The signed state is the same proof
    # of identity OTP-verify uses, so re-issuing here is safe.
    if not has_valid_session:
        new_token = issue_session(
            session,
            user_id=decoded.user_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        redirect.set_cookie(
            key=settings.session_cookie_name,
            value=new_token,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
            path="/",
        )
        _log.info("oauth.google.session_reissued", extra={"user_id": decoded.user_id})

    return redirect


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


@router.post("/fetch-now")
def post_fetch_now(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> dict[str, Any]:
    """Trigger an immediate Gmail poll without waiting for the scheduled tick.

    Same path the background poller takes once every
    ``PLATFORM_GMAIL_POLL_INTERVAL_SECONDS`` seconds, but invoked
    synchronously in this request. Used by the "Fetch now" button on
    the business dashboard.
    """
    user, workspace = ctx
    _require_business(user)
    stats = gmail_source_service.fetch_now(session, workspace_id=workspace.id, user_id=user.id)
    return {
        "messages_scanned": stats.messages_scanned,
        "attachments_ingested": stats.attachments_ingested,
        "attachments_skipped": stats.attachments_skipped,
        "marked_disconnected": stats.marked_disconnected,
    }
