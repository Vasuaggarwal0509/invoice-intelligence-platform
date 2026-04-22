"""Extraction runner — glue between a queued job and the extraction_layer pipeline.

One entrypoint: :func:`run_job`. Called by the worker thread per job.
Walks through:

1. Load the inbox_message row → resolve the blob path + workspace id.
2. Read bytes; convert to ``numpy.ndarray`` via PIL.
3. Call ``extraction_layer.backend.app.pipeline.PipelineRunner.run``.
4. Serialise each stage output via ``Pydantic.model_dump_json``.
5. Write a ``pipeline_runs`` row.
6. Denormalise ValidationResult into ``validation_findings`` rows.
7. Project ExtractionResult fields back into the ``invoices`` row
   (vendor_name, client_name, invoice_no, etc.).
8. Flip ``inbox_messages.status`` to ``extracted``.

On any failure: flip status to ``failed`` and re-raise so the worker
can mark the job failed too.

The pipeline is IMPORTED from extraction_layer — not re-implemented.
We own only the persistence step.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from business_layer.errors import DependencyError, NotFoundError
from business_layer.repositories import inbox_messages as inbox_repo
from business_layer.repositories import invoices as invoices_repo
from business_layer.repositories import pipeline_runs as pipeline_runs_repo
from business_layer.repositories import validation_findings as findings_repo
from business_layer.repositories.jobs import JobRow
from business_layer.services import storage

# The extraction pipeline is imported from the sibling layer.
# `extraction_layer/` is the source of truth for all wire contracts;
# business_layer never re-implements it.
from extraction_layer.backend.app.pipeline import PipelineRunner

_log = logging.getLogger(__name__)

# Single pipeline instance per process — constructs OCR/extractor/
# table-extractor/validation-engine once. Expensive to build (loads
# OCR model weights), cheap to reuse.
_pipeline_singleton: PipelineRunner | None = None


def _get_pipeline() -> PipelineRunner:
    """Return the process-wide pipeline, building on first use."""
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = PipelineRunner()
    return _pipeline_singleton


# ``pipeline_version`` goes into the UNIQUE constraint on pipeline_runs,
# so re-runs with a different backend set live side-by-side. Bump this
# string when you change a stage's backend.
PIPELINE_VERSION = "ocr@rapidocr,extract@heuristic,tables@spatial,validate@default"


@dataclass(frozen=True)
class ExtractionSummary:
    """Return value of :func:`run_job` — what the worker marks on the job row."""

    invoice_id: str
    total_ms: float
    pass_count: int
    fail_count: int


def run_job(session: Session, *, job: JobRow) -> ExtractionSummary:
    """Run the full pipeline for a single job. Commits session on success."""
    # (1) inbox message lookup.
    inbox = inbox_repo.find_by_id_for_workspace(
        session,
        message_id=job.inbox_message_id,
        workspace_id=job.workspace_id,
    )
    if inbox is None:
        raise NotFoundError(
            "inbox message for job not found",
            context={"job_id": job.id},
        )
    if job.invoice_id is None:
        raise NotFoundError(
            "job has no invoice_id (upload didn't create a skeleton)",
            context={"job_id": job.id},
        )

    # Flip inbox to 'extracting' so the inbox viewer shows progress.
    inbox_repo.update_status(session, message_id=inbox.id, status="extracting")
    session.commit()

    # (2) bytes → numpy image.
    try:
        raw = storage.read_blob(inbox.file_storage_key)
        image = _bytes_to_ndarray(raw, inbox.content_type)
    except Exception as exc:  # pragma: no cover - exercised via integration
        _fail(session, inbox_id=inbox.id)
        raise DependencyError(
            "failed to decode uploaded bytes as an image",
            context={"job_id": job.id, "content_type": inbox.content_type},
        ) from exc

    # (3) run the pipeline.
    started = time.perf_counter()
    try:
        ocr_result, extraction_result, tables_result, validation_result = (
            _get_pipeline().run(image)
        )
    except Exception as exc:
        _fail(session, inbox_id=inbox.id)
        raise DependencyError(
            "extraction pipeline crashed",
            context={"job_id": job.id, "stage": "pipeline"},
        ) from exc
    total_ms = (time.perf_counter() - started) * 1000.0

    # (4) serialise stage outputs.
    ocr_json = ocr_result.model_dump_json()
    extraction_json = extraction_result.model_dump_json()
    tables_json = tables_result.model_dump_json()
    validation_json = (
        validation_result.model_dump_json() if validation_result is not None else None
    )

    # (5) persist pipeline_runs.
    pipeline_runs_repo.create(
        session,
        workspace_id=job.workspace_id,
        invoice_id=job.invoice_id,
        pipeline_version=PIPELINE_VERSION,
        ocr_result_json=ocr_json,
        extraction_result_json=extraction_json,
        tables_result_json=tables_json,
        validation_result_json=validation_json,
        ocr_ms=float(getattr(ocr_result, "duration_ms", 0.0)) or None,
        extract_ms=None,  # extraction stage doesn't yet emit timings per-stage
        tables_ms=None,
        validate_ms=None,
        total_ms=total_ms,
    )

    # (6) denormalise validation_findings for filterable dashboards.
    #
    # ``RuleOutcome`` values are lowercase at runtime ('pass' / 'fail' /
    # 'not_applicable') per the extraction_layer enum. The
    # validation_findings table's CHECK constraint uses UPPERCASE —
    # we canonicalise on the way in so the DB keeps a stable casing
    # and the wire-format response type can use the shorter names.
    pass_count = 0
    fail_count = 0
    finding_rows: list[dict] = []
    if validation_result is not None:
        for finding in validation_result.findings:
            raw = finding.outcome.value if hasattr(finding.outcome, "value") else str(finding.outcome)
            outcome_upper = raw.upper()
            finding_rows.append(
                {
                    "rule_name": finding.rule_name,
                    "target": finding.target,
                    "outcome": outcome_upper,
                    "reason": finding.reason,
                    "expected": _stringify(finding.expected),
                    "observed": _stringify(finding.observed),
                }
            )
            if outcome_upper == "PASS":
                pass_count += 1
            elif outcome_upper == "FAIL":
                fail_count += 1
    findings_repo.replace_for_invoice(
        session,
        invoice_id=job.invoice_id,
        workspace_id=job.workspace_id,
        findings=finding_rows,
    )

    # (7) project extracted fields into the invoice row.
    extracted = _extract_projectable_fields(extraction_result)
    invoices_repo.update_extracted_fields(
        session,
        invoice_id=job.invoice_id,
        **extracted,
    )

    # (8) flip inbox status.
    inbox_repo.update_status(session, message_id=inbox.id, status="extracted")

    session.commit()
    return ExtractionSummary(
        invoice_id=job.invoice_id,
        total_ms=total_ms,
        pass_count=pass_count,
        fail_count=fail_count,
    )


# ---------- helpers ----------------------------------------------------


def _bytes_to_ndarray(data: bytes, content_type: str) -> np.ndarray:
    """Decode stored bytes to a H×W×3 uint8 numpy array.

    RapidOCR accepts several input types, but the existing pipeline
    runner (``extraction_layer.backend.app.pipeline.PipelineRunner.run``)
    expects ``numpy.ndarray``. PDFs are not yet supported by the
    pipeline — we reject them earlier at upload? No — we allow them
    and fail here with a clear error. Sprint 5+ adds PDF rendering.
    """
    if content_type == "application/pdf":
        raise ValueError(
            "PDF extraction is not wired up yet — upload image formats (PNG/JPG/TIFF/WebP) for now"
        )
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def _extract_projectable_fields(extraction_result) -> dict:  # type: ignore[no-untyped-def]
    """Pull out the six columns we store on ``invoices``.

    :class:`ExtractionResult.fields` is a ``dict[str, ExtractedField]``
    keyed by field name (e.g. ``'invoice_no'``, ``'seller'``). We
    pick the ones that have a 1:1 mapping to invoice columns;
    everything else stays in the JSON blob for forensics.
    """
    # field-name key → invoices column
    mapping = {
        "invoice_no": "invoice_no",
        "invoice_date": "invoice_date",
        "seller": "vendor_name",
        "client": "client_name",
        "seller_tax_id": "seller_gstin",
        "client_tax_id": "client_gstin",
    }
    out: dict[str, str | None] = {v: None for v in mapping.values()}
    fields_dict = getattr(extraction_result, "fields", {}) or {}
    for name, column in mapping.items():
        field = fields_dict.get(name)
        if field is not None and getattr(field, "value", None):
            out[column] = str(field.value)
    return out


def _stringify(v) -> str | None:  # type: ignore[no-untyped-def]
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return str(v)
    try:
        import json
        return json.dumps(v)
    except Exception:
        return str(v)


def _fail(session: Session, *, inbox_id: str) -> None:
    """Best-effort: mark inbox as failed + commit so status is visible."""
    try:
        inbox_repo.update_status(session, message_id=inbox_id, status="failed")
        session.commit()
    except Exception:
        session.rollback()
