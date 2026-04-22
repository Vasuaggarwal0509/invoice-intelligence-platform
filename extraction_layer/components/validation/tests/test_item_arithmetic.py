"""Tests for per-item arithmetic consistency rules."""

import pytest

from extraction_layer.components.validation.rules.item_arithmetic import (
    validate_all_items,
    validate_item_gross_worth,
    validate_item_net_worth,
)
from extraction_layer.components.validation.types import RuleOutcome

from ._fixtures import make_item, make_tables


class TestNetWorthConsistency:
    def test_exact_match_passes(self):
        item = make_item(qty="2,00", net_price="10,00", net_worth="20,00")
        f = validate_item_net_worth(item, 0)
        assert f.outcome == RuleOutcome.PASS

    def test_within_rounding_tolerance(self):
        # 3 * 1,99 = 5,97 — exact
        item = make_item(qty="3,00", net_price="1,99", net_worth="5,97")
        assert validate_item_net_worth(item, 0).outcome == RuleOutcome.PASS

    def test_within_absolute_tolerance(self):
        # Computed 444,60 * 2 = 889,20; observed 889,19 (1 cent off).
        item = make_item(qty="2,00", net_price="444,60", net_worth="889,19")
        assert validate_item_net_worth(item, 0).outcome == RuleOutcome.PASS

    def test_above_tolerance_fails(self):
        item = make_item(qty="2,00", net_price="10,00", net_worth="25,00")
        f = validate_item_net_worth(item, 0)
        assert f.outcome == RuleOutcome.FAIL
        assert f.expected is not None
        assert f.observed == "25,00" or "25" in f.observed

    def test_missing_qty_is_not_applicable(self):
        item = make_item(qty=None, net_price="10,00", net_worth="20,00")
        assert validate_item_net_worth(item, 0).outcome == RuleOutcome.NOT_APPLICABLE

    def test_unparseable_value_is_not_applicable(self):
        item = make_item(qty="abc", net_price="10,00", net_worth="20,00")
        assert validate_item_net_worth(item, 0).outcome == RuleOutcome.NOT_APPLICABLE

    def test_target_includes_item_index(self):
        item = make_item()
        assert validate_item_net_worth(item, 3).target == "item[3].net_worth"

    def test_large_numbers_use_relative_tolerance(self):
        # 100 * 99,99 = 9999,00; observed 9999,95 (0.05 diff, within 1 % * 9999).
        item = make_item(qty="100,00", net_price="99,99", net_worth="9999,95")
        assert validate_item_net_worth(item, 0).outcome == RuleOutcome.PASS


class TestGrossWorthConsistency:
    def test_exact_10_percent(self):
        item = make_item(net_worth="20,00", vat="10%", gross_worth="22,00")
        assert validate_item_gross_worth(item, 0).outcome == RuleOutcome.PASS

    def test_within_rounding(self):
        # 5,97 * 1,10 = 6,567; observed 6,57 (rounded).
        item = make_item(net_worth="5,97", vat="10%", gross_worth="6,57")
        assert validate_item_gross_worth(item, 0).outcome == RuleOutcome.PASS

    def test_wrong_vat_fails(self):
        # 20 * 1,10 = 22 but observed claims 33 (50 %).
        item = make_item(net_worth="20,00", vat="10%", gross_worth="33,00")
        assert validate_item_gross_worth(item, 0).outcome == RuleOutcome.FAIL

    def test_missing_vat_is_not_applicable(self):
        item = make_item(net_worth="20,00", vat=None, gross_worth="22,00")
        assert validate_item_gross_worth(item, 0).outcome == RuleOutcome.NOT_APPLICABLE

    def test_zero_vat(self):
        item = make_item(net_worth="20,00", vat="0%", gross_worth="20,00")
        assert validate_item_gross_worth(item, 0).outcome == RuleOutcome.PASS


class TestValidateAllItems:
    def test_runs_two_rules_per_item(self):
        tables = make_tables(items=[make_item(), make_item(qty="3,00", net_price="2,00", net_worth="6,00", vat="10%", gross_worth="6,60")])
        findings = validate_all_items(tables)
        # 2 rules per item × 2 items = 4 findings
        assert len(findings) == 4
        # Every finding should reference one of the two rule names.
        rule_names = {f.rule_name for f in findings}
        assert rule_names == {"item_net_worth_consistency", "item_gross_worth_consistency"}

    def test_empty_items_returns_no_findings(self):
        tables = make_tables(items=[])
        findings = validate_all_items(tables)
        assert findings == []

    def test_mix_of_pass_fail(self):
        # Item 2 has a bad net_worth (2 × 10 ≠ 50) but its gross_worth is
        # set to match that bad net_worth (50 × 1.10 = 55), so only the
        # net_worth rule should fail on item 2.
        tables = make_tables(
            items=[
                make_item(qty="2,00", net_price="10,00", net_worth="20,00"),  # both PASS
                make_item(
                    qty="2,00", net_price="10,00", net_worth="50,00",
                    vat="10%", gross_worth="55,00",
                ),  # net_worth FAIL, gross_worth PASS vs the claimed net_worth
            ]
        )
        findings = validate_all_items(tables)
        outcomes = [f.outcome for f in findings]
        assert outcomes.count(RuleOutcome.PASS) == 3
        assert outcomes.count(RuleOutcome.FAIL) == 1
