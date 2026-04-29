"""CA-persona auth routes — signup + login (email+password).

Logout uses the shared ``/api/auth/logout`` from the business flow;
session cookies are persona-agnostic (the session row's user_id is
what matters).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from business_layer.config import Settings
from business_layer.models.ca import (
    CaLoginRequest,
    CaSessionResponse,
    CaSignupRequest,
    CaWorkspacePublic,
)
from business_layer.services.ca_auth_service import login_ca, signup_ca

from .deps import client_ip_dep, session_dep, settings_dep, user_agent_dep

router = APIRouter(prefix="/api/ca/auth", tags=["ca-auth"])


def _to_session_response(
    user_id: str, display_name: str, email: str, workspace
) -> CaSessionResponse:  # type: ignore[no-untyped-def]
    return CaSessionResponse(
        user_id=user_id,
        display_name=display_name,
        email=email,
        workspace=CaWorkspacePublic(
            id=workspace.id,
            name=workspace.name,
            gstin=workspace.gstin,
            role="ca",
        ),
    )


@router.post("/signup", response_model=CaSessionResponse, status_code=201)
def post_signup(
    body: CaSignupRequest,
    response: Response,
    session: Session = Depends(session_dep),
    client_ip: str = Depends(client_ip_dep),
    user_agent: str | None = Depends(user_agent_dep),
    settings: Settings = Depends(settings_dep),
) -> CaSessionResponse:
    """CA signup — returns the new session cookie + public identity."""
    result = signup_ca(
        session,
        email=str(body.email),
        password=body.password.get_secret_value(),
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
    return _to_session_response(
        user_id=result.user.id,
        display_name=result.user.display_name,
        email=result.user.email or "",
        workspace=result.workspace,
    )


@router.post("/login", response_model=CaSessionResponse)
def post_login(
    body: CaLoginRequest,
    response: Response,
    session: Session = Depends(session_dep),
    client_ip: str = Depends(client_ip_dep),
    user_agent: str | None = Depends(user_agent_dep),
    settings: Settings = Depends(settings_dep),
) -> CaSessionResponse:
    """CA login by email + password."""
    result = login_ca(
        session,
        email=str(body.email),
        password=body.password.get_secret_value(),
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
    return _to_session_response(
        user_id=result.user.id,
        display_name=result.user.display_name,
        email=result.user.email or "",
        workspace=result.workspace,
    )
