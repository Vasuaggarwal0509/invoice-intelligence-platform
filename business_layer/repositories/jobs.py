"""jobs table — the extraction work queue.

Single-consumer queue: one worker thread per process. The claim
pattern is SELECT + UPDATE guarded by state='queued' — if the UPDATE
affects 0 rows, someone beat us to it and we try again. Good enough
for v1 (one worker, single uvicorn); Sprint 5+ can swap to Postgres
``FOR UPDATE SKIP LOCKED`` or a real broker without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import asc, insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import jobs

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class JobRow:
    id: str
    workspace_id: str
    inbox_message_id: str
    invoice_id: str | None
    stage: str
    state: str
    attempts: int
    max_attempts: int
    next_run_at: int
    started_at: int | None
    finished_at: int | None
    error_message: str | None
    created_at: int


def _row_to_dc(row: Any) -> JobRow:
    return JobRow(
        id=row.id,
        workspace_id=row.workspace_id,
        inbox_message_id=row.inbox_message_id,
        invoice_id=row.invoice_id,
        stage=row.stage,
        state=row.state,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        next_run_at=row.next_run_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error_message=row.error_message,
        created_at=row.created_at,
    )


def create(
    session: Session,
    *,
    workspace_id: str,
    inbox_message_id: str,
    invoice_id: str | None,
    stage: str = "full",
) -> JobRow:
    jid = new_id()
    now = now_ms()
    session.execute(
        insert(jobs).values(
            id=jid,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            invoice_id=invoice_id,
            stage=stage,
            state="queued",
            attempts=0,
            max_attempts=3,
            next_run_at=now,
            started_at=None,
            finished_at=None,
            error_message=None,
            created_at=now,
        )
    )
    row = session.execute(select(jobs).where(jobs.c.id == jid)).first()
    assert row is not None
    return _row_to_dc(row)


def claim_next(session: Session) -> JobRow | None:
    """Atomically claim one queued job whose ``next_run_at`` is due.

    Returns ``None`` if there's nothing to do. Implementation:

    1. SELECT the oldest due queued job id.
    2. UPDATE it to state='running' WHERE state='queued' AND id=...
       If the rowcount is 0, someone else grabbed it — return None.
    """
    now = now_ms()
    candidate = session.execute(
        select(jobs.c.id)
        .where(jobs.c.state == "queued", jobs.c.next_run_at <= now)
        .order_by(asc(jobs.c.next_run_at))
        .limit(1)
    ).first()
    if candidate is None:
        return None

    result = session.execute(
        update(jobs)
        .where(jobs.c.id == candidate.id, jobs.c.state == "queued")
        .values(state="running", started_at=now, attempts=jobs.c.attempts + 1)
    )
    session.commit()
    if result.rowcount != 1:
        # Lost the race — another worker flipped state first.
        return None

    row = session.execute(select(jobs).where(jobs.c.id == candidate.id)).first()
    assert row is not None
    return _row_to_dc(row)


def mark_done(session: Session, *, job_id: str) -> None:
    session.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(state="done", finished_at=now_ms(), error_message=None)
    )


def mark_failed(session: Session, *, job_id: str, error: str) -> None:
    session.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(state="failed", finished_at=now_ms(), error_message=error[:500])
    )


def find_by_id(session: Session, job_id: str) -> JobRow | None:
    row = session.execute(select(jobs).where(jobs.c.id == job_id)).first()
    return _row_to_dc(row) if row else None
