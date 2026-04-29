"""Health / readiness endpoint.

``GET /health`` — returns 200 when the app + its dependencies are up,
503 otherwise. Body shape (success):

    {
      "status": "ok",
      "version": "0.0.1",
      "git_sha": "abc12345",
      "checks": {"db": "ok"}
    }

Body shape (failure):

    {
      "status": "degraded",
      "version": "0.0.1",
      "git_sha": "abc12345",
      "checks": {"db": "fail"},
      "reason": "dependency_unavailable"
    }

Render's ``healthCheckPath`` reads this; a 503 response causes Render
to mark the deploy unhealthy and roll back rather than serve broken
traffic.

Why include version + git_sha:
  * Lets oncall correlate "incident at 14:32" with "build abc12345"
    without grepping commit logs.
  * Cheap to produce — both come from a string read at app boot.

Why no auth:
  * Load balancers / uptime monitors must hit this without credentials.
  * Body contains no PII and no sensitive config.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from business_layer.services.health_service import is_healthy
from business_layer.version_info import get_git_sha, get_version

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> JSONResponse:
    """Return 200 if healthy; 503 otherwise."""
    db_ok = is_healthy()
    body = {
        "status": "ok" if db_ok else "degraded",
        "version": get_version(),
        "git_sha": get_git_sha(),
        "checks": {"db": "ok" if db_ok else "fail"},
    }
    if db_ok:
        return JSONResponse(status_code=200, content=body)
    body["reason"] = "dependency_unavailable"
    return JSONResponse(status_code=503, content=body)
