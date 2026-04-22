"""Pydantic wire-layer DTOs (request / response / domain).

Three flavours, never mixed:

- Request models live under ``*_request.py``, ``ConfigDict(extra='forbid')``.
- Response models live under ``*_response.py``, project-safe fields only.
- Domain models are private to services; carry invariants across service
  boundaries.

Sprint 0 ships ``common.py`` (error envelope, pagination, id types) only;
feature DTOs arrive in Sprint 1+.
"""
