import pytest
from langchain_core.messages import AIMessage

from src.agents import ModelOutputError, build_drafter, build_reviewer, format_drafter_human
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
        [FailedRule(rule="timeline", reason="promised 5 days not in notes")],
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


# --- absent/degraded model output (fail-closed inside the chain) ------------


def test_reviewer_none_verdict_raises_typed_error():
    # Structured output returning None (no tool call) must raise, not flow on.
    review = build_reviewer(ScriptedModel(review_responses=[None]), "system")
    with pytest.raises(ModelOutputError):
        review("draft", "notes")


def test_reviewer_none_verdict_triggers_fallback():
    # The raise happens INSIDE the primary chain, so a configured fallback fires.
    primary = ScriptedModel(review_responses=[None])
    fallback = ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")])
    review = build_reviewer(primary, "system", fallback_model=fallback)
    assert review("draft", "notes").verdict == "pass"


def test_drafter_joins_block_list_content():
    # Anthropic content can be a list of blocks; the drafter must return a str.
    blocks = [{"type": "text", "text": "part1 "}, {"type": "text", "text": "part2"}]
    draft = build_drafter(ScriptedModel(draft_responses=[blocks]), "system")
    assert draft("msg", "notes") == "part1 part2"


def test_drafter_empty_output_raises_typed_error():
    draft = build_drafter(ScriptedModel(draft_responses=["   "]), "system")
    with pytest.raises(ModelOutputError):
        draft("msg", "notes")


def test_drafter_empty_output_triggers_fallback_and_normalizes():
    primary = ScriptedModel(draft_responses=[""])
    fallback = ScriptedModel(draft_responses=["fallback draft body"])
    draft = build_drafter(primary, "system", fallback_model=fallback)
    out = draft("msg", "notes")
    assert out == "fallback draft body"
    assert isinstance(out, str)


def test_drafter_empty_fallback_output_also_raises():
    primary = ScriptedModel(draft_responses=[""])
    fallback = ScriptedModel(draft_responses=[""])
    draft = build_drafter(primary, "system", fallback_model=fallback)
    with pytest.raises(ModelOutputError):
        draft("msg", "notes")
