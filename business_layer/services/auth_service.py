"""Auth service — OTP request, verify, session issue/revoke, session resolve.

Sprint 1 surface (phone+OTP only for business owners):

* :func:`request_otp` — rate-limit, generate code, persist hash, return plaintext.
* :func:`verify_otp_and_start_session` — check code, create user+workspace
  if new, issue session token, persist hash, return result.
* :func:`revoke_session` — logout; revoke by the plaintext token we got
  from the cookie.
* :func:`resolve_session` — used by the ``get_current_user`` dep to
  turn a cookie into a user + workspace.

All functions:
* Raise :class:`PlatformError` subclasses — never FastAPI types.
* Take an explicit ``Session`` — the route/dep layer manages commit
  boundaries via ``get_session()``.
* Write to the events log on every state-changing action, never with
  PII.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.config import Settings, get_settings
from business_layer.errors import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from business_layer.repositories import events as events_repo
from business_layer.repositories import otp_challenges as otp_repo
from business_layer.repositories import sessions as sessions_repo
from business_layer.repositories import users as users_repo
from business_layer.repositories import workspaces as workspaces_repo
from business_layer.repositories.users import UserRow
from business_layer.repositories.workspaces import WorkspaceRow
from business_layer.security import otp as otp_sec
from business_layer.security import sessions as sessions_sec
from business_layer.security.rate_limit import limiter as rate_limiter

from .onboarding_service import signup_business

_log = logging.getLogger(__name__)


# ---------- OTP request ------------------------------------------------


@dataclass(frozen=True)
class OtpIssueResult:
    """What the OTP-request service returns.

    Attributes:
        plaintext: The 6-digit code to deliver via SMS. In dev this is
            logged to stdout by the route layer; in prod an SMS provider
            is hooked in. NEVER log from this service — keep the code
            in memory only.
        was_existing_user: True if the phone matches an existing user.
            Lets the frontend decide whether to collect display_name
            on the next step.
    """

    plaintext: str
    was_existing_user: bool


def request_otp(
    session: Session,
    *,
    phone: str,
    client_ip: str,
) -> OtpIssueResult:
    """Issue a fresh OTP challenge for ``phone``.

    Rate-limited by ``(phone, ip)`` to blunt both targeted bombardment
    of one user AND broad credential-probing from one IP.
    """
    settings = get_settings()

    # Rate limit per IP — prevents one caller spamming N phones.
    rate_limiter.check(
        f"otp_request:ip:{client_ip}",
        capacity=settings.rate_limit_otp_per_min,
        per_seconds=60,
    )
    # Rate limit per phone — prevents targeted SMS-bombing one victim.
    rate_limiter.check(
        f"otp_request:phone:{phone}",
        capacity=settings.rate_limit_otp_per_min,
        per_seconds=60,
    )

    # Generate + store hash only.
    issued = otp_sec.issue_otp()
    otp_repo.create(
        session,
        phone=phone,
        code_hash=issued.code_hash,
        purpose="login",
        ttl_seconds=settings.otp_ttl_seconds,
        max_attempts=settings.otp_max_attempts,
    )

    existing = users_repo.find_by_phone(session, phone)
    was_existing = existing is not None

    events_repo.append(
        session,
        action="auth.otp.requested",
        actor_user_id=existing.id if existing else None,
        metadata={"existing_user": was_existing},
    )
    _log.info(
        "auth.otp.requested",
        extra={"phone_prefix": phone[:3] + "***", "existing_user": was_existing},
    )
    return OtpIssueResult(plaintext=issued.plaintext, was_existing_user=was_existing)


# ---------- OTP verify + session issue ---------------------------------


@dataclass(frozen=True)
class VerifyResult:
    """Return value of :func:`verify_otp_and_start_session`."""

    user: UserRow
    workspace: WorkspaceRow
    session_token_plaintext: str
    is_new_user: bool


def verify_otp_and_start_session(
    session: Session,
    *,
    phone: str,
    code: str,
    display_name: str | None,
    gstin: str | None,
    client_ip: str,
    user_agent: str | None,
) -> VerifyResult:
    """Verify ``code`` against the active OTP; on success, issue a session.

    If the phone has no user row, ``display_name`` is required and a
    new user + workspace is created atomically before the session
    issues.

    Raises:
        AuthenticationError: OTP missing / expired / wrong.
        BusinessRuleError: Signup path without ``display_name``.
        ConflictError: Race against another signup for the same phone.
    """
    settings = get_settings()

    # Rate limit verify attempts too — per phone, tighter.
    rate_limiter.check(
        f"otp_verify:phone:{phone}",
        capacity=settings.rate_limit_otp_per_min,
        per_seconds=60,
    )

    challenge = otp_repo.find_latest_active(
        session, phone=phone, purpose="login"
    )
    if challenge is None:
        _log.info("auth.otp.verify.no_active_challenge", extra={"phone_prefix": phone[:3] + "***"})
        raise AuthenticationError("invalid or expired code")

    # Constant-time compare. Regardless of result, increment attempts
    # FIRST — ensures a passing-comparison path + a failing path touch
    # the DB symmetrically (harder to mine via timing).
    #
    # CRITICAL: commit the attempts increment BEFORE the verify check.
    # If we don't, an AuthenticationError raised below rolls back the
    # whole request transaction — including the increment — and the
    # challenge never hits its max_attempts cap. That turns the 6-digit
    # OTP into an unbounded brute-force target.
    otp_repo.increment_attempts(session, challenge_id=challenge.id)
    session.commit()

    if not otp_sec.verify_otp(code, challenge.code_hash):
        events_repo.append(
            session,
            action="auth.otp.verify.failed",
            metadata={"reason": "mismatch"},
        )
        # event is informational; commit it too so the audit log is
        # kept in sync with the attempt counter.
        session.commit()
        raise AuthenticationError("invalid or expired code")

    # Mark used before the branch below so a duplicate verify of the
    # same code re-fails as "no active challenge".
    otp_repo.mark_used(session, challenge_id=challenge.id)

    # Does a user exist? If so, login. If not, signup (display_name required).
    existing = users_repo.find_by_phone(session, phone)
    is_new_user = existing is None

    if is_new_user:
        if not display_name:
            raise BusinessRuleError(
                "display_name is required when signing up",
                context={"phone_prefix": phone[:3] + "***"},
            )
        # Race guard: another request in the same millisecond could
        # have claimed this phone. find_by_phone again right before
        # insert is a best-effort — the unique constraint is the
        # authoritative defence.
        race_user = users_repo.find_by_phone(session, phone)
        if race_user is not None:
            raise ConflictError("phone already registered")
        result = signup_business(
            session,
            phone=phone,
            display_name=display_name,
            gstin=gstin,
        )
        user, workspace = result.user, result.workspace
    else:
        assert existing is not None
        user = existing
        ws = workspaces_repo.find_by_owner(session, owner_user_id=user.id)
        if ws is None:
            # Should never happen — signup creates both atomically.
            # Raising BusinessRule rather than NotFound because from the
            # caller's perspective this is "your account is in a bad
            # state", not "the thing you asked for doesn't exist".
            raise BusinessRuleError(
                "user has no workspace",
                context={"user_id": user.id},
            )
        workspace = ws

    # Reset any lingering failed-login state on successful auth.
    users_repo.clear_failed_logins(session, user_id=user.id)
    users_repo.update_last_login(session, user_id=user.id)

    # Issue the session token — plaintext goes to the cookie, hash to
    # the DB.
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
        action="auth.login.succeeded" if not is_new_user else "auth.signup.succeeded",
        workspace_id=workspace.id,
        actor_user_id=user.id,
    )

    return VerifyResult(
        user=user,
        workspace=workspace,
        session_token_plaintext=issued.plaintext,
        is_new_user=is_new_user,
    )


# ---------- Session resolve / revoke -----------------------------------


@dataclass(frozen=True)
class ResolvedSession:
    user: UserRow
    workspace: WorkspaceRow


def resolve_session(session: Session, *, token_plaintext: str) -> ResolvedSession:
    """Turn a cookie-delivered plaintext token into a (user, workspace).

    Raises:
        AuthenticationError: Token missing, wrong, expired, or revoked.
    """
    if not token_plaintext:
        raise AuthenticationError("not authenticated")

    token_hash = sessions_sec.hash_token(token_plaintext)
    row = sessions_repo.find_active_by_hash(session, token_hash=token_hash)
    if row is None:
        raise AuthenticationError("not authenticated")

    user = users_repo.find_by_id(session, row.user_id)
    if user is None:
        # Orphaned session — user was deleted. Treat as not authenticated;
        # revoke to keep the DB tidy.
        sessions_repo.revoke_by_hash(session, token_hash=token_hash)
        raise AuthenticationError("not authenticated")

    workspace = workspaces_repo.find_by_owner(session, owner_user_id=user.id)
    if workspace is None:
        raise BusinessRuleError(
            "user has no workspace",
            context={"user_id": user.id},
        )

    return ResolvedSession(user=user, workspace=workspace)


def revoke_session(session: Session, *, token_plaintext: str) -> None:
    """Revoke a session by its plaintext token. Idempotent; never raises."""
    if not token_plaintext:
        return
    token_hash = sessions_sec.hash_token(token_plaintext)
    sessions_repo.revoke_by_hash(session, token_hash=token_hash)
    events_repo.append(
        session,
        action="auth.logout",
    )
