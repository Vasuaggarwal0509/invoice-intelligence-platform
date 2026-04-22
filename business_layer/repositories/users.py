"""users table queries.

Returns :class:`UserRow` dataclasses — deliberately NOT Pydantic. Keeps
the DB layer ignorant of wire-format types; the service layer maps
``UserRow`` to :class:`business_layer.models.auth.UserPublic` before
anything leaves the process.

Everything uses parameterized SQLAlchemy Core. No f-string SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import users

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class UserRow:
    """Row shape returned by user repository reads.

    Matches the DB schema; not to be exposed to API responses. The
    service layer projects a subset of these fields into
    :class:`UserPublic`.
    """

    id: str
    role: str
    email: str | None
    phone: str | None
    password_hash: str | None
    display_name: str
    created_at: int
    last_login_at: int | None
    locked_until: int | None
    failed_login_count: int


def _row_to_dc(row: Any) -> UserRow:
    return UserRow(
        id=row.id,
        role=row.role,
        email=row.email,
        phone=row.phone,
        password_hash=row.password_hash,
        display_name=row.display_name,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
        locked_until=row.locked_until,
        failed_login_count=row.failed_login_count,
    )


# ---------- Reads ------------------------------------------------------


def find_by_phone(session: Session, phone: str) -> UserRow | None:
    """Return the user with matching ``phone``, or None."""
    row = session.execute(select(users).where(users.c.phone == phone)).first()
    return _row_to_dc(row) if row else None


def find_by_id(session: Session, user_id: str) -> UserRow | None:
    row = session.execute(select(users).where(users.c.id == user_id)).first()
    return _row_to_dc(row) if row else None


def find_by_email(session: Session, email: str) -> UserRow | None:
    row = session.execute(select(users).where(users.c.email == email)).first()
    return _row_to_dc(row) if row else None


# ---------- Writes -----------------------------------------------------


def create(
    session: Session,
    *,
    role: str,
    display_name: str,
    phone: str | None = None,
    email: str | None = None,
    password_hash: str | None = None,
) -> UserRow:
    """Insert a new user and return the persisted row.

    Caller is responsible for checking that the ``phone`` / ``email``
    isn't already in use — the unique constraint will raise, but the
    service layer surfaces a :class:`ConflictError` with better context
    before we reach the DB.
    """
    uid = new_id()
    session.execute(
        insert(users).values(
            id=uid,
            role=role,
            phone=phone,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            created_at=now_ms(),
            failed_login_count=0,
        )
    )
    row = find_by_id(session, uid)
    assert row is not None  # just inserted
    return row


def increment_failed_login(
    session: Session,
    *,
    user_id: str,
    lockout_after: int,
    lockout_seconds: int,
) -> UserRow:
    """Record one failed-login attempt; lock the account if threshold reached.

    Returns the updated row so callers can observe the new state
    (e.g. to tell the user they've been locked out).
    """
    current = find_by_id(session, user_id)
    assert current is not None  # caller just authenticated against it
    new_count = current.failed_login_count + 1
    locked_until = (
        now_ms() + lockout_seconds * 1000 if new_count >= lockout_after else None
    )
    session.execute(
        update(users)
        .where(users.c.id == user_id)
        .values(
            failed_login_count=new_count,
            locked_until=locked_until,
        )
    )
    row = find_by_id(session, user_id)
    assert row is not None
    return row


def clear_failed_logins(session: Session, *, user_id: str) -> None:
    """Zero the failure counter and lift the lockout — on successful login."""
    session.execute(
        update(users)
        .where(users.c.id == user_id)
        .values(failed_login_count=0, locked_until=None)
    )


def update_last_login(session: Session, *, user_id: str) -> None:
    session.execute(
        update(users).where(users.c.id == user_id).values(last_login_at=now_ms())
    )


def is_locked(user: UserRow) -> bool:
    """Pure predicate over a :class:`UserRow` snapshot — no DB I/O.

    Kept on the repository module so the lockout semantics live in one
    place. Service-layer callers use this to decide whether to even
    attempt a password verify.
    """
    return user.locked_until is not None and user.locked_until > now_ms()
