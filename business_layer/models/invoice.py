"""Invoice detail DTOs.

Business persona today gets the "plain-language" projection. The full
validation rule breakdown ships to the CA persona in Sprint 4 and
references the same backing data — so this module exposes BOTH views
via separate response models. The route for each persona picks the
right one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ValidationFindingPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_name: str
    target: str | None = None
    outcome: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    reason: str | None = None
    expected: str | None = None
    observed: str | None = None


class InvoiceSummary(BaseModel):
    """Plain-language invoice view for the business persona.

    No extraction confidence, no rule-level breakdown — just the facts
    the owner wants: "who, how much, when, is it a duplicate?".
    """

    model_config = ConfigDict(frozen=True)

    id: str
    status: Literal["pending", "under_review", "approved", "rejected", "flagged"]
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_amount_minor: int | None
    currency: str
    source_kind: str
    received_at: int
    extraction_status: Literal["queued", "extracting", "extracted", "failed", "ignored"]
    findings_summary: dict[str, int]                 # {pass, fail, not_applicable}
    image_url: str                                    # /api/invoices/{id}/image — workspace-gated


class InvoiceDetailBusiness(BaseModel):
    """Business-persona detail — summary + the bare validation flags."""

    model_config = ConfigDict(frozen=True)

    invoice: InvoiceSummary
    flags: list[ValidationFindingPublic]            # failing findings only


class InvoiceDetailCa(BaseModel):
    """CA-persona detail — everything the business view has PLUS raw pipeline JSON.

    Shipped in Sprint 4 with the CA shell. Defined here so the types
    module stays one import boundary for every invoice response.
    """

    model_config = ConfigDict(frozen=True)

    invoice: InvoiceSummary
    findings: list[ValidationFindingPublic]
    ocr_result: dict[str, Any] | None = None
    extraction_result: dict[str, Any] | None = None
    tables_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    pipeline_version: str | None = None
    total_ms: float | None = None
