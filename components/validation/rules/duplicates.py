"""
Exact-match duplicate detection within a batch.

Given a sequence of `ExtractionResult`s from a single batch, emit one
`RuleFinding` per extraction that has a duplicate key with any other
extraction in the batch. Duplicate key tuple:

    (invoice_no, seller_tax_id, invoice_date)

A duplicate is flagged on **both** records (so no record silently
survives). MinHash LSH near-duplicate detection is deferred (see
`research.md` §11.4).
"""

from collections import defaultdict

from components.extraction.types import ExtractionResult

from ..types import RuleFinding, RuleOutcome


def detect_duplicates(batch: list[ExtractionResult]) -> list[list[RuleFinding]]:
    """Find exact-match duplicate records in a batch.

    Args:
        batch: sequence of ExtractionResults, one per invoice.

    Returns:
        A list the same length as `batch`. Index i holds the findings for
        `batch[i]` (usually one ``batch_duplicate`` finding — PASS or FAIL).
        Records with None on any part of the key produce NOT_APPLICABLE.
    """
    key_to_indices: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    keys: list[tuple[str, str, str] | None] = []
    for record in batch:
        inv = record.get_value("invoice_no")
        tax = record.get_value("seller_tax_id")
        date = record.get_value("invoice_date")
        if inv is None or tax is None or date is None:
            keys.append(None)
            continue
        key = (inv, tax, date)
        keys.append(key)
        key_to_indices[key].append(len(keys) - 1)

    findings_by_index: list[list[RuleFinding]] = []
    for i, key in enumerate(keys):
        if key is None:
            findings_by_index.append(
                [
                    RuleFinding(
                        rule_name="batch_duplicate",
                        target="record",
                        outcome=RuleOutcome.NOT_APPLICABLE,
                        reason="missing invoice_no / seller_tax_id / invoice_date",
                    )
                ]
            )
            continue
        same_key = key_to_indices.get(key, [])
        if len(same_key) <= 1:
            findings_by_index.append(
                [
                    RuleFinding(
                        rule_name="batch_duplicate",
                        target="record",
                        outcome=RuleOutcome.PASS,
                    )
                ]
            )
        else:
            others = [idx for idx in same_key if idx != i]
            reason = (
                f"duplicate (invoice_no, seller_tax_id, invoice_date) "
                f"with batch index(es) {sorted(others)}"
            )
            findings_by_index.append(
                [
                    RuleFinding(
                        rule_name="batch_duplicate",
                        target="record",
                        outcome=RuleOutcome.FAIL,
                        reason=reason,
                        observed=f"{key[0]} / {key[1]} / {key[2]}",
                    )
                ]
            )
    return findings_by_index
