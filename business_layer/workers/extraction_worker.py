"""In-process extraction worker thread.

Single worker per process. Polls ``jobs`` for queued rows, runs the
extraction pipeline, marks the job done/failed. Simple today; the
interface is the pluggable seam for Sprint 5+ (Redis/Celery/SQS).

Lifecycle:

* :func:`start` is called from the FastAPI startup hook.
* :func:`stop` is called from the FastAPI shutdown hook.
* Both are idempotent — safe to call twice (tests exercise this).

Failure policy:

* ``NotFoundError`` on stale jobs → marks failed immediately, no retry.
* Any other exception → marks failed and logs with the job id for
  correlation with events + request_id.
* No automatic retries in v1 — job.attempts is incremented on every
  claim, but nothing re-queues a failed job. Sprint 4+ adds backoff.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from business_layer.db import get_session
from business_layer.repositories import jobs as jobs_repo
from business_layer.services.extraction_runner import run_job

_log = logging.getLogger(__name__)


class ExtractionWorker:
    """Thin wrapper around a background thread + stop signal.

    Kept as a class (rather than a bare thread) so tests can hold a
    handle, stop it deterministically, and introspect state.
    """

    def __init__(self, *, poll_interval_seconds: float = 0.5) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._poll_interval = poll_interval_seconds

    def start(self) -> None:
        """Start the worker thread. No-op if already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            name="extraction-worker",
            daemon=True,  # exit with the process; no lingering thread on crash
        )
        self._thread.start()
        _log.info("worker.started")

    def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the worker to exit and wait up to ``timeout`` seconds."""
        self._stop_event.set()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
        _log.info("worker.stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------- internals -------------------------------------------------

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self._drain_once()
            except Exception:
                # Worker thread must never die silently. Log + keep
                # going; individual job failures are handled inside
                # _drain_once.
                _log.exception("worker.tick_error")
                processed = False

            if not processed:
                # Nothing to do — sleep a bit before polling again.
                # Use the stop_event.wait so stop() is instantaneous.
                self._stop_event.wait(self._poll_interval)

    def _drain_once(self) -> bool:
        """Pull and process exactly one job; return True if we did any work."""
        with get_session() as session:
            job = jobs_repo.claim_next(session)
        if job is None:
            return False

        _log.info("worker.claim", extra={"job_id": job.id, "workspace_id": job.workspace_id})
        try:
            with get_session() as session:
                summary = run_job(session, job=job)
                # run_job commits internally; we still need to mark the
                # job done afterwards in a fresh session.
            with get_session() as session:
                jobs_repo.mark_done(session, job_id=job.id)
            _log.info(
                "worker.job_done",
                extra={
                    "job_id": job.id,
                    "invoice_id": summary.invoice_id,
                    "total_ms": summary.total_ms,
                    "pass": summary.pass_count,
                    "fail": summary.fail_count,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised by manual smoke
            _log.exception("worker.job_failed", extra={"job_id": job.id})
            try:
                with get_session() as session:
                    jobs_repo.mark_failed(session, job_id=job.id, error=str(exc))
            except Exception:
                _log.exception("worker.mark_failed_error", extra={"job_id": job.id})
        return True


# Module-level handle — the FastAPI app owns the instance's lifecycle.
# Tests construct their own ExtractionWorker and bypass this global.
worker = ExtractionWorker()


# Convenience seam for tests: run the queue synchronously without a
# thread. Keeps test timing deterministic.
def drain_now(processor: Callable[..., None] | None = None) -> int:
    """Pull every currently-queued job and process it inline.

    Used by tests after issuing an upload, so we can assert on the
    pipeline outcome without timing assumptions. Returns the number
    of jobs processed.
    """
    count = 0
    while True:
        with get_session() as session:
            job = jobs_repo.claim_next(session)
        if job is None:
            return count
        try:
            with get_session() as session:
                run_job(session, job=job)
            with get_session() as session:
                jobs_repo.mark_done(session, job_id=job.id)
        except Exception as exc:
            with get_session() as session:
                jobs_repo.mark_failed(session, job_id=job.id, error=str(exc))
            raise
        count += 1
