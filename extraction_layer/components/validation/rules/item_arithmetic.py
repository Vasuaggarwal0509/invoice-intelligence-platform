"""
Per-item arithmetic consistency rules.

For each line item we check the two natural invariants:

    net_worth   ≈ qty × net_price
    gross_worth ≈ net_worth × (1 + VAT/100)

Tolerance is combined absolute + relative: ``abs(expected - observed)
≤ max(1.0, expected * 0.01)``. This accommodates both large-amount
invoices (where a 1-unit absolute tolerance would be too strict) and
small-amount invoices (where a percent-only tolerance would let
1-unit errors slide).

Each check emits one `RuleFinding`. Missing inputs produce
NOT_APPLICABLE — a genuinely missing field is an extraction bug,
not an arithmetic bug.
"""

from decimal import Decimal

from extraction_layer.components.tables.types import InvoiceItem, TableExtractionResult

from ..parsers import parse_european_decimal, parse_percent
from ..types import RuleFinding, RuleOutcome

_ABS_TOL = Decimal("1.0")
_REL_TOL = Decimal("0.01")


def _within_tolerance(expected: Decimal, observed: Decimal) -> bool:
    diff = abs(expected - observed)
    allowed = max(_ABS_TOL, abs(expected) * _REL_TOL)
    return diff <= allowed


def _net_worth_target(index: int) -> str:
    return f"item[{index}].net_worth"


def _gross_worth_target(index: int) -> str:
    return f"item[{index}].gross_worth"


def validate_item_net_worth(item: InvoiceItem, index: int) -> RuleFinding:
    """Check that ``qty × net_price ≈ net_worth`` for one item."""
    qty = parse_european_decimal(item.item_qty)
    net_price = parse_european_decimal(item.item_net_price)
    net_worth = parse_european_decimal(item.item_net_worth)

    if qty is None or net_price is None or net_worth is None:
        return RuleFinding(
            rule_name="item_net_worth_consistency",
            target=_net_worth_target(index),
            outcome=RuleOutcome.NOT_APPLICABLE,
            reason="missing or unparseable qty / net_price / net_worth",
        )

    expected = qty * net_price
    if _within_tolerance(expected, net_worth):
        return RuleFinding(
            rule_name="item_net_worth_consistency",
            target=_net_worth_target(index),
            outcome=RuleOutcome.PASS,
        )
    return RuleFinding(
        rule_name="item_net_worth_consistency",
        target=_net_worth_target(index),
        outcome=RuleOutcome.FAIL,
        reason="net_worth != qty * net_price beyond tolerance",
        expected=str(expected),
        observed=str(net_worth),
    )


def validate_item_gross_worth(item: InvoiceItem, index: int) -> RuleFinding:
    """Check that ``net_worth × (1 + VAT/100) ≈ gross_worth`` for one item."""
    net_worth = parse_european_decimal(item.item_net_worth)
    vat = parse_percent(item.item_vat)
    gross_worth = parse_european_decimal(item.item_gross_worth)

    if net_worth is None or vat is None or gross_worth is None:
        return RuleFinding(
            rule_name="item_gross_worth_consistency",
            target=_gross_worth_target(index),
            outcome=RuleOutcome.NOT_APPLICABLE,
            reason="missing or unparseable net_worth / vat / gross_worth",
        )

    expected = net_worth * (Decimal(1) + vat / Decimal(100))
    if _within_tolerance(expected, gross_worth):
        return RuleFinding(
            rule_name="item_gross_worth_consistency",
            target=_gross_worth_target(index),
            outcome=RuleOutcome.PASS,
        )
    return RuleFinding(
        rule_name="item_gross_worth_consistency",
        target=_gross_worth_target(index),
        outcome=RuleOutcome.FAIL,
        reason="gross_worth != net_worth * (1 + VAT/100) beyond tolerance",
        expected=str(expected),
        observed=str(gross_worth),
    )


def validate_all_items(tables: TableExtractionResult) -> list[RuleFinding]:
    """Run both item-arithmetic rules on every item in a TableExtractionResult."""
    findings: list[RuleFinding] = []
    for i, item in enumerate(tables.items):
        findings.append(validate_item_net_worth(item, i))
        findings.append(validate_item_gross_worth(item, i))
    return findings
