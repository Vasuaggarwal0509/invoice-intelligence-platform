"""Tests for the validation output types."""

import pytest
from pydantic import ValidationError

from extraction_layer.components.validation.types import RuleFinding, RuleOutcome, ValidationResult


class TestRuleFinding:
    def test_valid_pass(self):
        f = RuleFinding(rule_name="x", target="y", outcome=RuleOutcome.PASS)
        assert f.outcome == RuleOutcome.PASS
        assert f.reason is None

    def test_fail_with_reason(self):
        f = RuleFinding(
            rule_name="iban_checksum",
            target="iban",
            outcome=RuleOutcome.FAIL,
            reason="mod-97 mismatch",
            observed="GB00BAD1234",
        )
        assert f.reason == "mod-97 mismatch"
        assert f.observed == "GB00BAD1234"

    def test_rule_name_required(self):
        with pytest.raises(ValidationError):
            RuleFinding(rule_name="", target="y", outcome=RuleOutcome.PASS)

    def test_target_required(self):
        with pytest.raises(ValidationError):
            RuleFinding(rule_name="x", target="", outcome=RuleOutcome.PASS)

    def test_frozen(self):
        f = RuleFinding(rule_name="x", target="y", outcome=RuleOutcome.PASS)
        with pytest.raises((ValidationError, TypeError)):
            f.outcome = RuleOutcome.FAIL


class TestValidationResult:
    def test_empty_result(self):
        r = ValidationResult()
        assert r.findings == []
        assert r.pass_count() == 0
        assert r.fail_count() == 0
        assert r.not_applicable_count() == 0
        assert r.all_checks_pass() is True

    def test_all_pass(self):
        r = ValidationResult(
            findings=[
                RuleFinding(rule_name="a", target="x", outcome=RuleOutcome.PASS),
                RuleFinding(rule_name="b", target="y", outcome=RuleOutcome.PASS),
            ]
        )
        assert r.pass_count() == 2
        assert r.fail_count() == 0
        assert r.all_checks_pass() is True

    def test_with_failures(self):
        r = ValidationResult(
            findings=[
                RuleFinding(rule_name="a", target="x", outcome=RuleOutcome.PASS),
                RuleFinding(rule_name="b", target="y", outcome=RuleOutcome.FAIL, reason="bad"),
            ]
        )
        assert r.pass_count() == 1
        assert r.fail_count() == 1
        assert r.all_checks_pass() is False
        failures = r.failures()
        assert len(failures) == 1
        assert failures[0].rule_name == "b"

    def test_not_applicable_does_not_count_as_fail(self):
        r = ValidationResult(
            findings=[
                RuleFinding(rule_name="a", target="x", outcome=RuleOutcome.PASS),
                RuleFinding(rule_name="b", target="y", outcome=RuleOutcome.NOT_APPLICABLE),
            ]
        )
        assert r.all_checks_pass() is True
        assert r.summary() == {"pass": 1, "fail": 0, "not_applicable": 1}

    def test_json_roundtrip(self):
        r = ValidationResult(
            findings=[
                RuleFinding(rule_name="a", target="x", outcome=RuleOutcome.PASS),
            ]
        )
        dumped = r.model_dump_json()
        roundtrip = ValidationResult.model_validate_json(dumped)
        assert roundtrip.findings[0].rule_name == "a"
        assert roundtrip.findings[0].outcome == RuleOutcome.PASS
