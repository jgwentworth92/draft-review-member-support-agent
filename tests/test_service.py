import pytest
from pydantic import ValidationError

from src.config import load_config
from src.schemas import ReviewVerdict, RunResult
from src.service import DraftReviewService
from tests.stub_model import ScriptedModel


def _svc(drafter, reviewer):
    return DraftReviewService(
        load_config("config.yaml"), drafter_model=drafter, reviewer_model=reviewer
    )


def test_run_returns_typed_runresult_on_pass():
    svc = _svc(
        ScriptedModel(draft_responses=["We can help. Please confirm the last 4 digits."]),
        ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")]),
    )
    result = svc.run("upset about a $50 charge", "Disputes can be filed.")
    assert isinstance(result, RunResult)
    assert result.status == "pending_human_review"
    assert result.draft
    assert result.rounds == 1
    assert result.review.verdict == "pass"
    assert result.review.failed_rules == []


def test_run_validates_empty_input():
    svc = _svc(ScriptedModel(), ScriptedModel())
    with pytest.raises(ValidationError):
        svc.run("", "notes")


def test_build_once_reuses_models_across_runs():
    # If the service rebuilt models per run, the 2nd run would NOT draw from the
    # injected stubs (it would build real models). Both runs succeeding off the
    # single injected stub sequence proves the pipeline is built once and reused.
    drafter = ScriptedModel(draft_responses=["d1. last 4 digits.", "d2. last 4 digits."])
    reviewer = ScriptedModel(
        review_responses=[ReviewVerdict(verdict="pass"), ReviewVerdict(verdict="pass")]
    )
    svc = _svc(drafter, reviewer)
    r1 = svc.run("m1", "n1")
    r2 = svc.run("m2", "n2")
    assert r1.status == "pending_human_review"
    assert r2.status == "pending_human_review"
