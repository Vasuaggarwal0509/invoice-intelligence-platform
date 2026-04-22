"""validation_findings — denormalised projection of ValidationResult rules.

Each RuleFinding becomes one row. Duplicates the info in
``pipeline_runs.validation_result_json``, but gives us indexed filtering
for the CA dashboard ("show me all invoices with GSTR-2B mismatches")
without parsing JSON in the query path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from business_layer.db.tables import validation_findings

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class ValidationFindingRow:
    id: str
    workspace_id: str
    invoice_id: str
    rule_name: str
    target: str | None
    outcome: str
    reason: str | None
    expected: str | None
    observed: str | None
    created_at: int


def _row_to_dc(row: Any) -> ValidationFindingRow:
    return ValidationFindingRow(
        id=row.id,
        workspace_id=row.workspace_id,
        invoice_id=row.invoice_id,
        rule_name=row.rule_name,
        target=row.target,
        outcome=row.outcome,
        reason=row.reason,
        expected=row.expected,
        observed=row.observed,
        created_at=row.created_at,
    )


def list_for_invoice(
    session: Session,
    *,
    invoice_id: str,
    workspace_id: str,
) -> list[ValidationFindingRow]:
    rows = session.execute(
        select(validation_findings).where(
            validation_findings.c.invoice_id == invoice_id,
            validation_findings.c.workspace_id == workspace_id,
        )
    ).all()
    return [_row_to_dc(r) for r in rows]


def replace_for_invoice(
    session: Session,
    *,
    invoice_id: str,
    workspace_id: str,
    findings: list[dict[str, Any]],
) -> None:
    """Delete existing findings for the invoice, then insert the new set.

    Used after a pipeline re-run — prevents stale findings from a
    prior run from lingering alongside fresh ones.

    ``findings`` is a list of dicts with keys:
    ``rule_name, target, outcome, reason, expected, observed``.
    """
    # Delete old findings for this invoice (scoped to workspace as a
    # belt-and-braces defence).
    session.execute(
        delete(validation_findings).where(
            validation_findings.c.invoice_id == invoice_id,
            validation_findings.c.workspace_id == workspace_id,
        )
    )
    if not findings:
        return
    now = now_ms()
    session.execute(
        insert(validation_findings),
        [
            {
                "id": new_id(),
                "workspace_id": workspace_id,
                "invoice_id": invoice_id,
                "rule_name": f["rule_name"],
                "target": f.get("target"),
                "outcome": f["outcome"],
                "reason": f.get("reason"),
                "expected": f.get("expected"),
                "observed": f.get("observed"),
                "created_at": now,
            }
            for f in findings
        ],
    )
