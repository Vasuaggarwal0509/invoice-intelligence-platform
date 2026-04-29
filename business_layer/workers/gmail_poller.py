"""Background poller for connected Gmail sources.

Same thread-based shape as :mod:`extraction_worker` — single worker
per process, idempotent start/stop. On each tick we iterate every
``sources`` row with ``kind='gmail' AND status='connected'`` and call
:func:`gmail_connector.pull_new_attachments`.

The per-source poll interval is global (from settings). A per-source
override column can be added later without changing this file.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from sqlalchemy import select

from business_layer.config import get_settings
from business_layer.db import get_session
from business_layer.db.tables import sources as t_sources
from business_layer.db.tables import workspaces as t_workspaces
from business_layer.repositories.sources import SourceRow, _row_to_dc
from business_layer.services.connectors import gmail_connector

_log = logging.getLogger(__name__)


@dataclass
class _SourceTask:
    source: SourceRow
    owner_user_id: str


class GmailPoller:
    """Background thread that polls every connected Gmail source."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gmail-poller", daemon=True)
        self._thread.start()
        _log.info("gmail_poller.started")

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
        _log.info("gmail_poller.stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------- internals ------------------------------------------------

    def _run(self) -> None:
        interval = max(60, get_settings().gmail_poll_interval_seconds)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                _log.exception("gmail_poller.tick_error")
            self._stop.wait(interval)

    def _tick(self) -> None:
        tasks = self._collect_tasks()
        if not tasks:
            return
        _log.info("gmail_poller.tick", extra={"source_count": len(tasks)})
        for t in tasks:
            try:
                with get_session() as s:
                    gmail_connector.pull_new_attachments(
                        s, source=t.source, user_id=t.owner_user_id
                    )
            except Exception:
                _log.exception(
                    "gmail_poller.source_failed",
                    extra={"source_id": t.source.id},
                )

    def _collect_tasks(self) -> list[_SourceTask]:
        """Query every connected Gmail source + its owning user id.

        Join via workspaces so the connector has the user_id it needs
        for events + upload audit trail.
        """
        with get_session() as s:
            rows = s.execute(
                select(
                    t_sources,
                    t_workspaces.c.owner_user_id.label("owner_user_id"),
                )
                .select_from(
                    t_sources.join(t_workspaces, t_workspaces.c.id == t_sources.c.workspace_id)
                )
                .where(
                    t_sources.c.kind == "gmail",
                    t_sources.c.status == "connected",
                )
            ).all()

        out: list[_SourceTask] = []
        for row in rows:
            source = _row_to_dc(row)
            out.append(_SourceTask(source=source, owner_user_id=row.owner_user_id))
        return out


# Module-level handle — FastAPI owns the instance's lifecycle.
poller = GmailPoller()


def tick_now() -> None:
    """Test helper — run one tick synchronously without a thread."""
    poller._tick()
