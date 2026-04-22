"""events table — append-only audit log.

No update / delete repository methods exist by design. Every meaningful
state transition in the app writes a row here; admin analytics read
exclusively from this table (plus ``workspaces`` + ``users``
metadata), never from ``invoices`` — the PII boundary described in
``docs/business_plan.md`` §7.5.

Events carry a JSON ``metadata`` bag. Convention: NO PII in metadata
(no phone numbers, email bodies, OCR text, extracted fields). Reviewable
by code review + by the PII redaction log processor added in later
sprints.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from business_layer.db.tables import events

from ._ids import new_id, now_ms


def append(
    session: Session,
    *,
    action: str,
    workspace_id: str | None = None,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one event row.

    ``action`` is a dotted string like ``"user.signed_up"`` or
    ``"auth.login.failed"``. Keep the namespace short — admin
    dashboards aggregate by ``action`` + ``ts``.
    """
    session.execute(
        insert(events).values(
            id=new_id(),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=json.dumps(metadata) if metadata else None,
            ts=now_ms(),
        )
    )
