"""CA-persona auth — email + password + argon2.

Business owners use phone+OTP (see :mod:`auth_service`). CA firms get
traditional email+password because:

* CA firms have employees who'd need separate accounts eventually —
  passwords scale better than one-SIM-per-person.
* CAs work from desktops primarily; OTP UX is an extra step.
* Password stretching (argon2id from :mod:`security.passwords`) keeps
  the worst case bounded if the DB ever leaks.

Login path uses the existing lockout counter on ``users`` (populated
by :func:`users_repo.increment_failed_login`). After
:data:`Settings.login_max_attempts` consecutive failures the account
locks for :data:`Settings.login_lockout_seconds`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.config import get_settings
from business_layer.errors import (
    AuthenticationError,
    ConflictError,
    ValidationError,
)
from business_layer.repositories import events as events_repo
from business_layer.repositories import sessions as sessions_repo
from business_layer.repositories import users as users_repo
from business_layer.repositories import workspaces as workspaces_repo
from business_layer.repositories.users import UserRow
from business_layer.repositories.workspaces import WorkspaceRow
from business_layer.security import passwords as pw
from business_layer.security import sessions as sessions_sec
from business_layer.security.rate_limit import limiter as rate_limiter

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaSignupResult:
    user: UserRow
    workspace: WorkspaceRow
    session_token_plaintext: str


@dataclass(frozen=True)
class CaLoginResult:
    user: UserRow
    workspace: WorkspaceRow
    session_token_plaintext: str


# ---------- signup -----------------------------------------------------


def signup_ca(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    gstin: str,
    client_ip: str,
    user_agent: str | None,
) -> CaSignupResult:
    """Create a CA user + workspace atomically, start a session.

    Raises:
        ConflictError: email already registered.
        ValidationError: missing/invalid GSTIN (empty).
    """
    settings = get_settings()
    rate_limiter.check(
        f"signup:ip:{client_ip}",
        capacity=settings.rate_limit_login_per_min,
        per_seconds=60,
    )

    if not gstin:
        raise ValidationError(
            "GSTIN is required for CA signup",
            context={"email_prefix": email.split("@")[0][:3] + "***"},
        )

    if users_repo.find_by_email(session, email) is not None:
        raise ConflictError("that email is already registered")

    # workspace.gstin for a CA = the CA firm's own GSTIN. Make sure no
    # other workspace already claims it — otherwise business lookups
    # would be ambiguous.
    if workspaces_repo.find_by_gstin(session, gstin=gstin) is not None:
        raise ConflictError("that GSTIN is already registered with another workspace")

    user = users_repo.create(
        session,
        role="ca",
        display_name=display_name,
        email=email,
        password_hash=pw.hash_password(password),
    )
    workspace = workspaces_repo.create(
        session,
        owner_user_id=user.id,
        name=display_name,
        gstin=gstin,
        created_via="self_signup",
        default_extraction_mode="instant",
        ca_gstin=None,  # CAs don't have a CA-of-their-own in v1
    )
    events_repo.append(
        session,
        action="ca.signed_up",
        workspace_id=workspace.id,
        actor_user_id=user.id,
        target_type="workspace",
        target_id=workspace.id,
        metadata={"role": "ca", "via": "email_password"},
    )

    issued = sessions_sec.issue_token()
    sessions_repo.create(
        session,
        user_id=user.id,
        token_hash=issued.token_hash,
        ttl_seconds=settings.session_ttl_seconds,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    _log.info(
        "ca.signup.complete",
        extra={"user_id": user.id, "workspace_id": workspace.id},
    )
    return CaSignupResult(
        user=user,
        workspace=workspace,
        session_token_plaintext=issued.plaintext,
    )


# ---------- login ------------------------------------------------------


def login_ca(
    session: Session,
    *,
    email: str,
    password: str,
    client_ip: str,
    user_agent: str | None,
) -> CaLoginResult:
    """Verify email+password, start a session.

    Generic 401 response on any failure — never tell the caller
    whether the email was unknown vs the password was wrong.

    Raises:
        AuthenticationError: credentials invalid OR account locked OR
            user is not a CA (business users go through phone+OTP).
    """
    settings = get_settings()

    # Per-IP login rate-limit: blunt credential stuffing.
    rate_limiter.check(
        f"login:ip:{client_ip}",
        capacity=settings.rate_limit_login_per_min,
        per_seconds=60,
    )

    user = users_repo.find_by_email(session, email)
    if user is None:
        # Constant-time-ish: still do a dummy hash verify so timing
        # doesn't distinguish "unknown email" from "wrong password".
        pw.verify_password(
            "$argon2id$v=19$m=65536,t=3,p=4$c29tZWR1bW15c2FsdA$" "c29tZWR1bW15aGFzaA",
            password,
        )
        raise AuthenticationError("invalid credentials")

    if user.role != "ca":
        # Business users must use the phone-OTP flow. Don't leak that
        # the email exists — same generic error.
        raise AuthenticationError("invalid credentials")

    if users_repo.is_locked(user):
        # Still generic. Lockout detail is admin-visible via events
        # log; users get "invalid credentials" to avoid revealing
        # counter state.
        raise AuthenticationError("invalid credentials")

    if user.password_hash is None or not pw.verify_password(user.password_hash, password):
        # Increment failure counter, commit before raising so it
        # persists (same pattern as OTP attempt accounting).
        users_repo.increment_failed_login(
            session,
            user_id=user.id,
            lockout_after=settings.login_max_attempts,
            lockout_seconds=settings.login_lockout_seconds,
        )
        session.commit()
        raise AuthenticationError("invalid credentials")

    # Rehash with current argon2 params if hash is from older settings.
    # users_repo.update_password_hash() lands in a later pass — for now,
    # the verification still works with any older hash, so a stale-param
    # hash is a security non-issue, just a future hygiene improvement.
    # (The needs_rehash check is left here as a marker so the next pass
    # has an obvious place to wire the update call into.)
    _ = pw.needs_rehash(user.password_hash)

    workspace = workspaces_repo.find_by_owner(session, owner_user_id=user.id)
    if workspace is None:
        # Data integrity issue — CA with no workspace shouldn't be
        # possible post-signup. Surface as a generic server-side
        # mismatch rather than auth.
        from business_layer.errors import InternalError

        raise InternalError("ca user has no workspace")

    users_repo.clear_failed_logins(session, user_id=user.id)
    users_repo.update_last_login(session, user_id=user.id)

    issued = sessions_sec.issue_token()
    sessions_repo.create(
        session,
        user_id=user.id,
        token_hash=issued.token_hash,
        ttl_seconds=settings.session_ttl_seconds,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    events_repo.append(
        session,
        action="ca.login.succeeded",
        workspace_id=workspace.id,
        actor_user_id=user.id,
    )
    _log.info("ca.login.succeeded", extra={"user_id": user.id})

    return CaLoginResult(
        user=user,
        workspace=workspace,
        session_token_plaintext=issued.plaintext,
    )
