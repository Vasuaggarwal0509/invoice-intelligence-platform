"""Onboarding — atomic "create user + workspace" for business signup.

A single function call creates both rows inside the caller's DB
session, so if either fails the transaction rolls back cleanly. Keeps
the two writes inseparable, which matches how users think about
signup (one conceptual action).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.repositories import events as events_repo
from business_layer.repositories import users as users_repo
from business_layer.repositories import workspaces as workspaces_repo
from business_layer.repositories.users import UserRow
from business_layer.repositories.workspaces import WorkspaceRow

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignupResult:
    """Return value of :func:`signup_business`."""

    user: UserRow
    workspace: WorkspaceRow


def signup_business(
    session: Session,
    *,
    phone: str,
    display_name: str,
    gstin: str | None = None,
) -> SignupResult:
    """Create a fresh business-role user + their single workspace.

    Both inserts happen inside ``session`` — commit/rollback is the
    caller's responsibility (normally the ``get_session()`` context
    manager in the route layer, which commits on clean exit).

    Idempotency: the repository's unique constraint on ``users.phone``
    will prevent duplicate signups. Service-layer callers should
    check ``users_repo.find_by_phone`` first and raise
    :class:`ConflictError` with friendlier context — the DB error
    leaks ``UNIQUE constraint failed`` which is ugly for users.
    """
    user = users_repo.create(
        session,
        role="business",
        display_name=display_name,
        phone=phone,
    )
    workspace = workspaces_repo.create(
        session,
        owner_user_id=user.id,
        name=display_name,
        gstin=gstin,
        created_via="self_signup",
        default_extraction_mode="instant",
    )
    events_repo.append(
        session,
        action="user.signed_up",
        workspace_id=workspace.id,
        actor_user_id=user.id,
        target_type="workspace",
        target_id=workspace.id,
        metadata={"role": "business", "via": "phone_otp"},
    )
    _log.info(
        "onboarding.signup_complete",
        extra={
            "user_id": user.id,
            "workspace_id": workspace.id,
            "role": "business",
        },
    )
    return SignupResult(user=user, workspace=workspace)
