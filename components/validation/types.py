"""
Output types for the validation component.

A `ValidationResult` contains a flat list of `RuleFinding`s — each a
structured (rule, target, outcome, reason) record. Downstream code —
UI, CSV export, batch reports — consumes the flat list uniformly and
decides policy (flag-for-review threshold, etc.) on its own terms.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleOutcome(str, Enum):
    """The three-state result of a validation rule."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"  # missing input / unreachable — not a failure


class RuleFinding(BaseModel):
    """A single rule's outcome for a single target."""

    model_config = ConfigDict(frozen=True)

    rule_name: str = Field(..., min_length=1, description="Rule identifier, e.g. 'iban_checksum'.")
    target: str = Field(
        ...,
        min_length=1,
        description="What the rule was checking. For field rules, the field name; "
        "for item rules, 'item[N]' + field; for cross-sample rules, a stable tag.",
    )
    outcome: RuleOutcome
    reason: str | None = Field(
        default=None,
        description="Human-readable explanation, mostly populated on FAIL or NOT_APPLICABLE.",
    )
    expected: str | None = Field(
        default=None,
        description="For numeric rules, the computed expected value (makes failures inspectable).",
    )
    observed: str | None = Field(
        default=None,
        description="For numeric rules, the actual observed value.",
    )


class ValidationResult(BaseModel):
    """Collection of rule findings from running the validation engine on one invoice."""

    model_config = ConfigDict(frozen=True)

    findings: list[RuleFinding] = Field(default_factory=list)
    source: str = Field(
        default="engine",
        min_length=1,
        description="Who produced this result (for audit trails).",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ----- convenience accessors ------------------------------------------

    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.outcome == RuleOutcome.PASS)

    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.outcome == RuleOutcome.FAIL)

    def not_applicable_count(self) -> int:
        return sum(1 for f in self.findings if f.outcome == RuleOutcome.NOT_APPLICABLE)

    def all_checks_pass(self) -> bool:
        """True if every rule that was applicable passed (NOT_APPLICABLE is fine)."""
        return self.fail_count() == 0

    def failures(self) -> list[RuleFinding]:
        return [f for f in self.findings if f.outcome == RuleOutcome.FAIL]

    def summary(self) -> dict[str, int]:
        return {
            "pass": self.pass_count(),
            "fail": self.fail_count(),
            "not_applicable": self.not_applicable_count(),
        }
