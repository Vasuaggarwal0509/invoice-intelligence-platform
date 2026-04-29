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
        ocr_result, extraction_result, tables_result, validation_result = _get_pipeline().run(image)
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
    validation_json = validation_result.model_dump_json() if validation_result is not None else None

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
            raw = (
                finding.outcome.value if hasattr(finding.outcome, "value") else str(finding.outcome)
            )
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

    # (7) project extracted fields + computed totals into the invoice row.
    extracted = _extract_projectable_fields(extraction_result)
    total_minor = _sum_items_to_minor(tables_result)
    if total_minor is not None:
        extracted["total_amount_minor"] = total_minor  # type: ignore[assignment]
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
    """Pull out the columns we denormalise onto ``invoices``.

    :class:`ExtractionResult.fields` is a ``dict[str, ExtractedField]``
    keyed by the canonical label names from
    :data:`extraction_layer.components.extraction.heuristic.labels.LABEL_VARIANTS`
    — ``seller``, ``client``, ``invoice_no``, ``date``, ``tax_id``.

    The extractor does NOT split ``tax_id`` into seller vs client; both
    entities' tax IDs land under one key. Convention: persist into
    ``seller_gstin`` since on Indian invoices the supplier's GSTIN is
    the one buyers reconcile against (the ITC-claim side). If we later
    wire a seller-vs-client disambiguator, the second value lands in
    ``client_gstin`` via the same projection.
    """
    # field-name key → invoices column
    mapping = {
        "invoice_no": "invoice_no",
        "date": "invoice_date",
        "seller": "vendor_name",
        "client": "client_name",
        "tax_id": "seller_gstin",
    }
    out: dict[str, str | None] = {v: None for v in mapping.values()}
    fields_dict = getattr(extraction_result, "fields", {}) or {}
    for name, column in mapping.items():
        field = fields_dict.get(name)
        if field is not None and getattr(field, "value", None):
            out[column] = str(field.value)
    return out


def _sum_items_to_minor(tables_result) -> int | None:  # type: ignore[no-untyped-def]
    """Sum ``item_gross_worth`` across items → total invoice amount in paise.

    Returns ``None`` if no parseable totals were found (all items
    blank or unparseable). We store money as INTEGER paise to avoid
    floating-point drift in aggregate KPIs.

    Parser is permissive — strips currency symbols, thousands separators,
    whitespace — because OCR output varies (``$ 1,234.56``, ``₹1234.56``,
    ``1 234,56``, etc.). Ambiguous European decimals (``1.234,56``) are
    coerced by the last-separator-wins heuristic which is good enough
    for Indian invoices (decimal dot, thousands comma).
    """
    items = getattr(tables_result, "items", []) or []
    if not items:
        return None

    total_paise = 0
    found_any = False
    for item in items:
        gross_s = getattr(item, "item_gross_worth", None)
        parsed = _parse_money_to_paise(gross_s)
        if parsed is not None:
            total_paise += parsed
            found_any = True
    return total_paise if found_any else None


def _parse_money_to_paise(raw: str | None) -> int | None:
    """Best-effort parse of a money string to integer paise.

    Returns None on empty / unparseable input — callers treat that as
    "no signal" and fall back to the previous value (or leave NULL).
    """
    if not raw:
        return None
    # Strip non-digit/dot/comma/minus characters (currency symbols,
    # whitespace, letters like "Rs.").
    cleaned = "".join(ch for ch in str(raw) if ch.isdigit() or ch in ".,-")
    if not cleaned or cleaned in {".", ",", "-"}:
        return None
    # Prefer the LAST separator as the decimal mark (handles "1,234.56"
    # and "1.234,56"). Everything before it with both separators stripped
    # is the integer part.
    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    decimal_idx = max(last_comma, last_dot)
    if decimal_idx == -1:
        # No decimal part — treat whole number.
        try:
            return int(cleaned) * 100
        except ValueError:
            return None
    int_part = cleaned[:decimal_idx].replace(",", "").replace(".", "")
    dec_part = cleaned[decimal_idx + 1 :]
    # Pad/truncate decimal to exactly 2 digits.
    if len(dec_part) >= 2:
        dec_part = dec_part[:2]
    else:
        dec_part = dec_part.ljust(2, "0")
    sign = -1 if int_part.startswith("-") else 1
    int_part = int_part.lstrip("-")
    try:
        return sign * (int(int_part or "0") * 100 + int(dec_part or "0"))
    except ValueError:
        return None


def _stringify(v) -> str | None:  # type: ignore[no-untyped-def]
    if v is None:
        return None
    if isinstance(v, str | int | float | bool):
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
