"""Auth routes — OTP request / verify, logout, current identity.

Routes here are thin: they parse the request, call the service, set
the cookie, return a wire-format DTO. No business logic beyond that.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from business_layer.config import Settings
from business_layer.models.auth import (
    OtpVerifyRequest,
    OtpRequestRequest,
    SessionResponse,
    SimpleStatus,
    UserPublic,
    WorkspacePublic,
)
from business_layer.services import UserRow, WorkspaceRow
from business_layer.services.auth_service import (
    request_otp,
    resolve_session,
    revoke_session,
    verify_otp_and_start_session,
)

from .deps import (
    client_ip_dep,
    current_context_dep,
    current_session_token_dep,
    session_dep,
    settings_dep,
    user_agent_dep,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_log = logging.getLogger(__name__)


def _public_user(row: UserRow) -> UserPublic:
    return UserPublic(
        id=row.id,
        role=row.role,  # type: ignore[arg-type]
        display_name=row.display_name,
        phone=row.phone,
    )


def _public_workspace(row: WorkspaceRow) -> WorkspacePublic:
    return WorkspacePublic(
        id=row.id,
        name=row.name,
        gstin=row.gstin,
        default_extraction_mode=row.default_extraction_mode,  # type: ignore[arg-type]
    )


@router.post("/otp/request", response_model=SimpleStatus)
def post_otp_request(
    body: OtpRequestRequest,
    session: Session = Depends(session_dep),
    client_ip: str = Depends(client_ip_dep),
    settings: Settings = Depends(settings_dep),
) -> SimpleStatus:
    """Request an OTP code.

    In dev (``PLATFORM_ENV != prod``), the plaintext code is logged
    server-side so the developer can read it from console output. In
    prod, an SMS provider is called (TODO Sprint 4). Either way, the
    body always returns the same generic "status=sent" — the response
    never reveals whether the phone is new or known.
    """
    result = request_otp(session, phone=body.phone, client_ip=client_ip)

    # Dev-only OTP display. Never log plaintext in prod.
    if settings.env != "prod":
        _log.info(
            "DEV_OTP_ISSUED phone=%s code=%s (existing_user=%s)",
            body.phone,
            result.plaintext,
            result.was_existing_user,
        )

    return SimpleStatus(status="sent")


@router.post("/otp/verify", response_model=SessionResponse)
def post_otp_verify(
    body: OtpVerifyRequest,
    response: Response,
    session: Session = Depends(session_dep),
    client_ip: str = Depends(client_ip_dep),
    user_agent: str | None = Depends(user_agent_dep),
    settings: Settings = Depends(settings_dep),
) -> SessionResponse:
    """Verify OTP; on success, create user+workspace (if new) and start a session.

    The cookie set here is HttpOnly, SameSite=Lax, Secure (per
    :class:`Settings`). Client-side JS cannot read it — the session
    lifecycle is entirely server-side.
    """
    result = verify_otp_and_start_session(
        session,
        phone=body.phone,
        code=body.code,
        display_name=body.display_name,
        gstin=body.gstin,
        client_ip=client_ip,
        user_agent=user_agent,
    )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=result.session_token_plaintext,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )

    return SessionResponse(
        user=_public_user(result.user),
        workspace=_public_workspace(result.workspace),
        is_new_user=result.is_new_user,
    )


@router.post("/logout", response_model=SimpleStatus)
def post_logout(
    response: Response,
    session: Session = Depends(session_dep),
    token: str = Depends(current_session_token_dep),
    settings: Settings = Depends(settings_dep),
) -> SimpleStatus:
    """Revoke the current session and clear the cookie.

    Idempotent — calling logout without a valid session is a no-op
    that still clears the cookie.
    """
    revoke_session(session, token_plaintext=token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
    )
    return SimpleStatus(status="logged_out")


@router.get("/me", response_model=SessionResponse)
def get_me(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
) -> SessionResponse:
    """Return the current user + their workspace; 401 if not signed in."""
    user, workspace = ctx
    return SessionResponse(
        user=_public_user(user),
        workspace=_public_workspace(workspace),
        is_new_user=False,
    )
