"""Inbox DTOs — wire-format for the unified-inbox viewer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class InboxRow(BaseModel):
    """One row in the inbox table.

    Fields that aren't populated until extraction completes (vendor,
    total) are optional; the frontend dims them when null.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    invoice_id: str | None
    source_kind: Literal["gmail", "outlook", "whatsapp", "upload", "folder"]
    sender: str | None
    subject: str | None                              # displayed as "File" for uploads
    received_at: int                                 # unix ms
    content_type: str
    status: Literal["queued", "extracting", "extracted", "failed", "ignored"]
    vendor_name: str | None
    total_amount_minor: int | None
    currency: str


class InboxListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[InboxRow]
    total: int
    offset: int
    limit: int


class UploadResponse(BaseModel):
    """What ``POST /api/upload`` returns on success."""

    model_config = ConfigDict(frozen=True)

    inbox_message_id: str
    invoice_id: str
    job_id: str
    was_duplicate: bool
    status: str = "queued"
