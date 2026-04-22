"""ID + time helpers used by every repository.

Centralised so a future swap (UUIDv4 → UUIDv7, unix-ms → unix-s) is a
one-line change instead of a grep hunt. Kept in the repositories
package because nothing above this layer should care what format ids
have — they're opaque to services and routes.
"""

from __future__ import annotations

import time
import uuid


def new_id() -> str:
    """Return a short, opaque row id.

    UUID4 hex for Sprint 1 — 128 bits of entropy, lexicographic ordering
    is unrelated to creation time. When we revisit for time-sortable
    ids we swap this to UUIDv7 without touching callers.
    """
    return uuid.uuid4().hex


def now_ms() -> int:
    """Current time in Unix milliseconds (same unit as every ``created_at`` column)."""
    return int(time.time() * 1000)
