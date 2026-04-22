"""Health / readiness checks.

Wraps the raw DB ping so the route layer stays layer-clean (routes → services
→ repositories → db). The service's job is trivial here, but setting the
pattern now means Sprint 1+ routes don't grow a habit of reaching past
services into db/ directly.
"""

from __future__ import annotations

from business_layer.db import ping as _db_ping


def is_healthy() -> bool:
    """Return True if the process + its dependencies are ready to serve traffic.

    Sprint 0: just the DB. Future sprints can extend this to check the
    job queue lag, OCR backend reachability, etc.
    """
    return _db_ping()
