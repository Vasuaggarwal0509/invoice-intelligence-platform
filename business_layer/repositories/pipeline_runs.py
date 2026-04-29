"""pipeline_runs table — one row per (invoice × pipeline_version).

Each of the four stage outputs (OCR, extraction, tables, validation)
is stored as its Pydantic ``model_dump_json()`` string. Reading a row
and rehydrating via ``Model.model_validate_json`` gives back a
fully-typed object identical to what the in-process pipeline
produces. This is the "wire contract" living in the DB.

We deliberately DON'T normalise these JSONs into columns. Reasons:

* The contracts are ``frozen=True`` Pydantic models governed by
  ``docs/CONTRACTS.md`` — stable enough to survive as opaque blobs.
* A re-run with a newer pipeline version is a NEW row, not an update.
  Old runs stay for forensics.
* Filterable projections the UI needs (rule outcomes, field flags)
  already exist as their own denormalised tables
  (:mod:`validation_findings`, :mod:`invoices`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, insert, select
from sqlalchemy.orm import Session

from business_layer.db.tables import pipeline_runs

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class PipelineRunRow:
    id: str
    workspace_id: str
    invoice_id: str
    pipeline_version: str
    ocr_result_json: str
    extraction_result_json: str
    tables_result_json: str
    validation_result_json: str | None
    ocr_ms: float | None
    extract_ms: float | None
    tables_ms: float | None
    validate_ms: float | None
    total_ms: float | None
    created_at: int


def _row_to_dc(row: Any) -> PipelineRunRow:
    return PipelineRunRow(
        id=row.id,
        workspace_id=row.workspace_id,
        invoice_id=row.invoice_id,
        pipeline_version=row.pipeline_version,
        ocr_result_json=row.ocr_result_json,
        extraction_result_json=row.extraction_result_json,
        tables_result_json=row.tables_result_json,
        validation_result_json=row.validation_result_json,
        ocr_ms=float(row.ocr_ms) if row.ocr_ms is not None else None,
        extract_ms=float(row.extract_ms) if row.extract_ms is not None else None,
        tables_ms=float(row.tables_ms) if row.tables_ms is not None else None,
        validate_ms=float(row.validate_ms) if row.validate_ms is not None else None,
        total_ms=float(row.total_ms) if row.total_ms is not None else None,
        created_at=row.created_at,
    )


def create(
    session: Session,
    *,
    workspace_id: str,
    invoice_id: str,
    pipeline_version: str,
    ocr_result_json: str,
    extraction_result_json: str,
    tables_result_json: str,
    validation_result_json: str | None,
    ocr_ms: float | None,
    extract_ms: float | None,
    tables_ms: float | None,
    validate_ms: float | None,
    total_ms: float | None,
) -> PipelineRunRow:
    pid = new_id()
    session.execute(
        insert(pipeline_runs).values(
            id=pid,
            workspace_id=workspace_id,
            invoice_id=invoice_id,
            pipeline_version=pipeline_version,
            ocr_result_json=ocr_result_json,
            extraction_result_json=extraction_result_json,
            tables_result_json=tables_result_json,
            validation_result_json=validation_result_json,
            ocr_ms=ocr_ms,
            extract_ms=extract_ms,
            tables_ms=tables_ms,
            validate_ms=validate_ms,
            total_ms=total_ms,
            created_at=now_ms(),
        )
    )
    row = session.execute(select(pipeline_runs).where(pipeline_runs.c.id == pid)).first()
    assert row is not None
    return _row_to_dc(row)


def find_latest_for_invoice(
    session: Session,
    *,
    invoice_id: str,
    workspace_id: str,
) -> PipelineRunRow | None:
    """Return the most recent pipeline run for an invoice, scoped by workspace."""
    row = session.execute(
        select(pipeline_runs)
        .where(
            pipeline_runs.c.invoice_id == invoice_id,
            pipeline_runs.c.workspace_id == workspace_id,
        )
        .order_by(desc(pipeline_runs.c.created_at))
        .limit(1)
    ).first()
    return _row_to_dc(row) if row else None
