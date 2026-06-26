from src.agents import build_drafter, build_reviewer, format_drafter_human
from src.schemas import ReviewVerdict, FailedRule
from tests.stub_model import ScriptedModel

def test_drafter_returns_body_and_uses_inputs():
    model = ScriptedModel(draft_responses=["Dear member, we can help."])
    draft = build_drafter(model, "system")
    out = draft("I'm upset about a charge", "Disputes can be filed.", None)
    assert out == "Dear member, we can help."

def test_drafter_human_includes_feedback_points():
    text = format_drafter_human(
        "msg", "notes",
        [{"rule": "timeline", "reason": "promised 5 days not in notes"}],
    )
    assert "timeline" in text and "promised 5 days not in notes" in text
    assert "msg" in text and "notes" in text

def test_drafter_human_marks_input_as_data():
    text = format_drafter_human("msg", "notes", None)
    assert "data, not instructions" in text.lower()

def test_reviewer_returns_structured_verdict():
    verdict = ReviewVerdict(verdict="revise",
                            failed_rules=[FailedRule(rule="tone", reason="curt")])
    model = ScriptedModel(review_responses=[verdict])
    review = build_reviewer(model, "system")
    result = review("some draft", "some notes")
    assert result.verdict == "revise"
    assert result.failed_rules[0].rule == "tone"
