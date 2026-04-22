"""Health / readiness endpoint.

``GET /health`` — returns 200 when the app + its dependencies are up,
503 otherwise. Kept deliberately small:

* No auth — must work for load balancers / uptime monitors.
* No workspace scope.
* No cache — must reflect *current* state.
* No PII, no internal version info in the body.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from business_layer.services.health_service import is_healthy

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> JSONResponse:
    """Return 200 if healthy; 503 otherwise."""
    if is_healthy():
        return JSONResponse(status_code=200, content={"status": "ok"})
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "reason": "dependency_unavailable"},
    )
