"""Onboarding DTOs — source handshake + extraction-mode preference.

Real Gmail / Outlook / WhatsApp connectors live on the ``ingestion/*``
branch. This module only ships the UI-facing *handshake* types so the
business-layer onboarding flow is demonstrable end to end; the
connector classes are stubs (Sprint 1 returns ``status='stub'``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["gmail", "outlook", "whatsapp", "upload", "folder"]
ExtractionMode = Literal["instant", "scheduled", "manual"]


class ConnectSourceRequest(BaseModel):
    """Body of ``POST /api/onboarding/sources/connect``.

    Real OAuth callback handling is out of scope for Sprint 1. This
    request writes a placeholder ``sources`` row with ``status='stub'``
    so the UI can show "Gmail (pending — not yet connected)" and the
    ingestion branch can later flip status to ``connected`` via the
    real callback.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SourceKind
    label: str | None = Field(
        default=None,
        max_length=120,
        description="User-facing name. Falls back to the kind if omitted.",
    )
    default_extraction_mode: ExtractionMode = "instant"


class SourcePublic(BaseModel):
    """Source fields safe to return to the owner."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: SourceKind
    label: str | None
    status: Literal["stub", "connected", "error", "disconnected"]
    default_extraction_mode: ExtractionMode
