import pytest
from pydantic import ValidationError
from src.schemas import FailedItem, ReviewVerdict, RunInput

def test_review_verdict_defaults_empty_failed_items():
    v = ReviewVerdict(verdict="pass")
    assert v.failed_items == []

def test_review_verdict_with_failures():
    v = ReviewVerdict(
        verdict="revise",
        failed_items=[FailedItem(item="timeline", reason="promises 5 days not in notes")],
    )
    assert v.failed_items[0].item == "timeline"

def test_review_verdict_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        ReviewVerdict(verdict="maybe")

def test_run_input_rejects_empty():
    with pytest.raises(ValidationError):
        RunInput(member_message="", case_notes="x")
