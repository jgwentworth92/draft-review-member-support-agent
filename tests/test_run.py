from src.run import run
from src.schemas import ReviewVerdict
from tests.stub_model import ScriptedModel


def test_run_with_injected_models_returns_final_state():
    drafter = ScriptedModel(draft_responses=["Compliant draft. Last 4 digits please."])
    reviewer = ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")])
    final = run("upset about $50 charge", "Disputes can be filed.",
                drafter_model=drafter, reviewer_model=reviewer)
    assert final["status"] == "pending_human_review"
    assert final["draft"]


def test_run_validates_empty_input():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        run("", "notes",
            drafter_model=ScriptedModel(), reviewer_model=ScriptedModel())
