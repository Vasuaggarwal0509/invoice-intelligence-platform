"""otp_challenges table queries.

An OTP challenge is single-use + time-bounded + attempt-bounded. The
repository exposes these three dimensions as explicit column reads so
services don't duplicate the check logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import otp_challenges

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class OtpChallengeRow:
    id: str
    phone: str
    code_hash: str
    purpose: str
    expires_at: int
    attempts: int
    max_attempts: int
    used_at: int | None
    created_at: int


def _row_to_dc(row: Any) -> OtpChallengeRow:
    return OtpChallengeRow(
        id=row.id,
        phone=row.phone,
        code_hash=row.code_hash,
        purpose=row.purpose,
        expires_at=row.expires_at,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        used_at=row.used_at,
        created_at=row.created_at,
    )


def create(
    session: Session,
    *,
    phone: str,
    code_hash: str,
    purpose: str,
    ttl_seconds: int,
    max_attempts: int,
) -> OtpChallengeRow:
    """Persist a freshly-generated OTP hash.

    Callers should NOT delete previous challenges for the same phone —
    attackers can't piggyback, because a new challenge supersedes the
    old in :func:`find_latest_active` via ``ORDER BY created_at DESC``.
    """
    cid = new_id()
    now = now_ms()
    session.execute(
        insert(otp_challenges).values(
            id=cid,
            phone=phone,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=now + ttl_seconds * 1000,
            attempts=0,
            max_attempts=max_attempts,
            used_at=None,
            created_at=now,
        )
    )
    row = session.execute(
        select(otp_challenges).where(otp_challenges.c.id == cid)
    ).first()
    assert row is not None
    return _row_to_dc(row)


def find_latest_active(
    session: Session,
    *,
    phone: str,
    purpose: str,
) -> OtpChallengeRow | None:
    """Return the most recent *active* challenge for this phone+purpose, or None.

    Active = unused AND unexpired AND attempts < max_attempts. The
    service layer should not need to re-check these conditions; if this
    returns a row, the row is usable.
    """
    now = now_ms()
    row = session.execute(
        select(otp_challenges)
        .where(
            otp_challenges.c.phone == phone,
            otp_challenges.c.purpose == purpose,
            otp_challenges.c.used_at.is_(None),
            otp_challenges.c.expires_at > now,
            otp_challenges.c.attempts < otp_challenges.c.max_attempts,
        )
        .order_by(desc(otp_challenges.c.created_at))
    ).first()
    return _row_to_dc(row) if row else None


def increment_attempts(session: Session, *, challenge_id: str) -> None:
    """Record a failed verify attempt against an active challenge."""
    session.execute(
        update(otp_challenges)
        .where(otp_challenges.c.id == challenge_id)
        .values(attempts=otp_challenges.c.attempts + 1)
    )


def mark_used(session: Session, *, challenge_id: str) -> None:
    """Mark a challenge consumed — idempotently safe to call after success."""
    session.execute(
        update(otp_challenges)
        .where(otp_challenges.c.id == challenge_id)
        .values(used_at=now_ms())
    )
