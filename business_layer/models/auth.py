"""Auth request/response DTOs.

Sprint 1 scope: phone + OTP only (business owner onboarding). CA
email+password arrives in Sprint 2.

Every request model is frozen + extra-forbid: unknown fields cause a
422 rather than silently getting dropped. This catches typos and
prevents the grows-over-time surface bug where a removed field sticks
around in a caller's payload.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import DisplayName, Gstin, OtpCode, Phone


class OtpRequestRequest(BaseModel):
    """Body of ``POST /api/auth/otp/request``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phone: Phone


class OtpVerifyRequest(BaseModel):
    """Body of ``POST /api/auth/otp/verify``.

    If the phone is new (no user exists), ``display_name`` is REQUIRED
    and the verify step also creates the user + workspace. For existing
    users the field is ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    phone: Phone
    code: OtpCode
    display_name: DisplayName | None = Field(
        default=None,
        description="Required on first-time signup; ignored for existing users.",
    )
    gstin: Gstin | None = Field(
        default=None,
        description="Optional — can be added later in settings.",
    )


class UserPublic(BaseModel):
    """User fields safe to return in API responses.

    Never include ``password_hash``, ``locked_until``,
    ``failed_login_count``, or phone/email when responding to a
    different user's session. This type is the only one allowed to
    flow out of /api/auth/me and siblings.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    role: Literal["business", "ca", "admin"]
    display_name: str
    phone: str | None = None


class WorkspacePublic(BaseModel):
    """Workspace fields safe to return in API responses."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    gstin: str | None = None
    default_extraction_mode: Literal["instant", "scheduled", "manual"]
    ca_gstin: str | None = None  # populated on business workspaces linked to a CA


class SessionResponse(BaseModel):
    """Body returned from OTP verify or /api/auth/me.

    The session token itself is NOT in the body — it's in the
    ``bl_session`` HttpOnly cookie. This body carries identity the
    frontend renders (current user + workspace).
    """

    model_config = ConfigDict(frozen=True)

    user: UserPublic
    workspace: WorkspacePublic
    is_new_user: bool = Field(
        default=False,
        description="True iff this call just created the user (signup path).",
    )


class SimpleStatus(BaseModel):
    """Body of ``POST /api/auth/logout`` and similar side-effect endpoints."""

    model_config = ConfigDict(frozen=True)

    status: str
