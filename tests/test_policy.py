"""Direct unit tests for the review policy - the rules the graph closure
previously made untestable in isolation."""

from __future__ import annotations

from src.guards import DEFAULT_CREDENTIAL_PATTERNS
from src.graph import route_after_review
from src.policy import apply_review_policy
from src.schemas import FailedRule, ReviewVerdict


def _policy(verdict_obj, draft):
    return apply_review_policy(verdict_obj, draft, list(DEFAULT_CREDENTIAL_PATTERNS))


def test_clean_pass_stays_pass():
    verdict, failed = _policy(ReviewVerdict(verdict="pass"), "A compliant draft.")
    assert verdict == "pass"
    assert failed == []


def test_pass_with_failed_rules_is_revise():
    # Invariant 2: pass is enforced in code, never trusted from the LLM string.
    verdict_obj = ReviewVerdict(
        verdict="pass", failed_rules=[FailedRule(rule="tone", reason="curt")]
    )
    verdict, failed = _policy(verdict_obj, "A draft.")
    assert verdict == "revise"
    assert failed[0].rule == "tone"


def test_credential_hit_overrides_llm_pass():
    verdict, failed = _policy(
        ReviewVerdict(verdict="pass"), "Please send your full card number."
    )
    assert verdict == "revise"
    assert any(fr.rule == "credential_request" for fr in failed)


def test_revise_keeps_reviewer_feedback_and_appends_guard_hit():
    verdict_obj = ReviewVerdict(
        verdict="revise", failed_rules=[FailedRule(rule="tone", reason="curt")]
    )
    verdict, failed = _policy(verdict_obj, "Please send your full card number.")
    assert verdict == "revise"
    assert [fr.rule for fr in failed] == ["tone", "credential_request"]


# --- routing: a guard hit on the final round must escalate -------------------


def test_route_pass_approves():
    assert route_after_review({"verdict": "pass", "round": 1}, max_rounds=3) == "approve"


def test_route_revise_below_cap_revises():
    assert route_after_review({"verdict": "revise", "round": 2}, max_rounds=3) == "revise"


def test_route_revise_at_cap_escalates():
    # The invariant the escalation guarantee rests on, asserted directly.
    assert route_after_review({"verdict": "revise", "round": 3}, max_rounds=3) == "escalate"
