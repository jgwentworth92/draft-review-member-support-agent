import pytest
from pydantic import ValidationError

from src.config import load_config
from src.schemas import FailedRule, ReviewVerdict, RunResult
from src.service import DraftReviewService
from tests.stub_model import ScriptedModel


def _svc(drafter, reviewer):
    return DraftReviewService(
        load_config("config.yaml"), drafter_model=drafter, reviewer_model=reviewer
    )


class _AlwaysRaisingReviewer:
    """Reviewer model whose structured runner raises on every call."""

    def with_structured_output(self, _schema):
        class _Runner:
            def invoke(self, _messages):
                raise RuntimeError("provider exploded")

        return _Runner()


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


# --- fail-closed boundary: every run ends in one of the two states ----------


def test_model_exception_escalates_instead_of_raising():
    # Invariant 1: an exception path must land in `escalated`, never propagate.
    svc = _svc(
        ScriptedModel(draft_responses=["a draft. last 4 digits."]),
        _AlwaysRaisingReviewer(),
    )
    result = svc.run("msg", "notes")
    assert result.status == "escalated"
    assert result.review.failed_rules[0].rule == "model_failure"
    assert result.draft is None


def test_reviewer_none_on_final_round_escalates():
    # A degraded reviewer on round max_rounds (3) must yield `escalated`,
    # never an exception or a third status.
    revise = ReviewVerdict(
        verdict="revise", failed_rules=[FailedRule(rule="tone", reason="curt")]
    )
    svc = _svc(
        ScriptedModel(draft_responses=["d1", "d2", "d3"]),
        ScriptedModel(review_responses=[revise, revise, None]),
    )
    result = svc.run("msg", "notes")
    assert result.status == "escalated"
    assert any(fr.rule == "model_failure" for fr in result.review.failed_rules)


def test_input_validation_error_still_propagates():
    # Caller-input errors are NOT model failures; they stay outside the boundary.
    svc = _svc(ScriptedModel(), ScriptedModel())
    with pytest.raises(ValidationError):
        svc.run("", "notes")


def test_reviewer_validation_error_escalates():
    # The ReviewVerdict validator turns revise-with-no-signal into a parse
    # error inside the chain; end to end that must land as escalated, not 503.
    class _InvalidVerdictReviewer:
        def with_structured_output(self, _schema):
            class _Runner:
                def invoke(self, _messages):
                    return ReviewVerdict(verdict="revise")  # raises ValidationError

            return _Runner()

    svc = _svc(ScriptedModel(draft_responses=["a draft"]), _InvalidVerdictReviewer())
    result = svc.run("msg", "notes")
    assert result.status == "escalated"
    assert result.review.failed_rules[0].rule == "model_failure"


# --- recursion limit covers the widest allowed max_rounds -------------------


def test_run_deadline_escalates():
    # A run that outlives loop.run_timeout_seconds must fail closed, not hang.
    # 0.5s sleep vs 0.05s deadline is a 10x margin - not timing-flaky.
    import time

    from langchain_core.messages import AIMessage

    class _SlowDrafter:
        def invoke(self, _messages):
            time.sleep(0.5)
            return AIMessage(content="slow draft")

    cfg = load_config("config.yaml")
    cfg.loop.run_timeout_seconds = 0.05
    svc = DraftReviewService(
        cfg, drafter_model=_SlowDrafter(), reviewer_model=ScriptedModel()
    )
    result = svc.run("msg", "notes")
    assert result.status == "escalated"
    assert "deadline" in result.review.failed_rules[0].reason


def test_max_rounds_eight_escalates_without_recursion_error():
    # max_rounds=8 needs 26 supersteps — over LangGraph's default limit of 25.
    # The service passes an explicit recursion_limit, so the cap must escalate
    # cleanly at the widest allowed setting.
    cfg = load_config("config.yaml")
    cfg.loop.max_rounds = 8
    revise = ReviewVerdict(
        verdict="revise", failed_rules=[FailedRule(rule="tone", reason="curt")]
    )
    svc = DraftReviewService(
        cfg,
        drafter_model=ScriptedModel(draft_responses=[f"d{i}" for i in range(1, 9)]),
        reviewer_model=ScriptedModel(review_responses=[revise] * 8),
    )
    result = svc.run("msg", "notes")
    assert result.status == "escalated"
    assert result.rounds == 8
