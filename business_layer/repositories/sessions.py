"""sessions table queries.

We persist **only** the SHA-256 hash of the session token — the
plaintext lives in the client's HttpOnly cookie and is never seen
server-side after the first issue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import sessions as t_sessions

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class SessionRow:
    id: str
    user_id: str
    token_hash: str
    expires_at: int
    user_agent: str | None
    ip_address: str | None
    revoked_at: int | None
    created_at: int


def _row_to_dc(row: Any) -> SessionRow:
    return SessionRow(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        user_agent=row.user_agent,
        ip_address=row.ip_address,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def create(
    session: Session,
    *,
    user_id: str,
    token_hash: str,
    ttl_seconds: int,
    user_agent: str | None,
    ip_address: str | None,
) -> SessionRow:
    """Persist a newly-issued session. Expires-at derived from TTL."""
    sid = new_id()
    now = now_ms()
    session.execute(
        insert(t_sessions).values(
            id=sid,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=now + ttl_seconds * 1000,
            user_agent=user_agent,
            ip_address=ip_address,
            revoked_at=None,
            created_at=now,
        )
    )
    row = session.execute(select(t_sessions).where(t_sessions.c.id == sid)).first()
    assert row is not None
    return _row_to_dc(row)


def find_active_by_hash(session: Session, *, token_hash: str) -> SessionRow | None:
    """Return the session iff the hash exists AND it's unrevoked AND unexpired.

    Three conditions combined in one query keep the attack surface
    small — no way to accidentally return a stale/revoked row.
    """
    now = now_ms()
    row = session.execute(
        select(t_sessions).where(
            t_sessions.c.token_hash == token_hash,
            t_sessions.c.revoked_at.is_(None),
            t_sessions.c.expires_at > now,
        )
    ).first()
    return _row_to_dc(row) if row else None


def revoke_by_hash(session: Session, *, token_hash: str) -> None:
    """Revoke a session immediately. Idempotent."""
    session.execute(
        update(t_sessions).where(t_sessions.c.token_hash == token_hash).values(revoked_at=now_ms())
    )
