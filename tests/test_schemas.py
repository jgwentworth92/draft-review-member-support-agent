import pytest
from pydantic import ValidationError
from src.scenarios.quality.schemas import FailedRule, ReviewVerdict, RunInput

def test_review_verdict_defaults_empty_failed_rules():
    v = ReviewVerdict(verdict="pass")
    assert v.failed_rules == []
    assert v.notes == ""

def test_review_verdict_with_failures():
    v = ReviewVerdict(
        verdict="revise",
        failed_rules=[FailedRule(rule="timeline", reason="promises 5 days not in notes")],
        notes="The timeline is not supported by the case notes.",
    )
    assert v.failed_rules[0].rule == "timeline"
    assert v.notes

def test_review_verdict_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        ReviewVerdict(verdict="maybe")

def test_run_input_rejects_empty():
    with pytest.raises(ValidationError):
        RunInput(member_message="", case_notes="x")
