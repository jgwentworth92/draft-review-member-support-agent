from __future__ import annotations

import logging

from src.core import guards
from src.core.runtime import retry_policy as _retry_policy
from src.core.topologies import critique_loop
from src.scenarios.quality.agents import build_drafter, build_reviewer
from src.scenarios.quality.config import AppConfig
from src.scenarios.quality.schemas import GraphState

# Frozen behavior: tests/test_logging.py captures the pre-refactor "src.graph"
# logger by name (caplog.at_level(..., logger="src.graph")). Logging under that
# same name preserves the original observability contract unchanged.
logger = logging.getLogger("src.graph")


def initial_state(member_message: str, case_notes: str) -> dict:
    return {
        "member_message": member_message,
        "case_notes": case_notes,
        "round": 1,
        "history": [],
    }


def build_app(
    config: AppConfig,
    drafter_model,
    reviewer_model,
    drafter_fallback=None,
    reviewer_fallback=None,
):
    drafter = build_drafter(drafter_model, config.drafter.system_prompt, drafter_fallback)
    reviewer = build_reviewer(reviewer_model, config.reviewer.system_prompt, reviewer_fallback)
    max_rounds = config.loop.max_rounds
    inj_patterns = config.guards.injection_patterns
    cred_patterns = config.guards.credential_patterns

    def guard_input_node(state: GraphState) -> dict:
        hits = guards.scan_input(state["member_message"], inj_patterns) + guards.scan_input(
            state["case_notes"], inj_patterns
        )
        if hits:
            logger.warning("Input guard escalated before drafting; injection patterns: %s", hits)
            return {
                "status": "escalated",
                "verdict": "revise",
                "feedback": [
                    {"rule": "prompt_injection", "reason": f"Injection patterns detected: {hits}"}
                ],
                "notes": "Escalated by the input guard before drafting.",
            }
        return {}

    def generator_node(state: GraphState) -> dict:
        draft = drafter(state["member_message"], state["case_notes"], state.get("feedback"))
        return {"draft": draft}

    def reviewer_node(state: GraphState) -> dict:
        verdict_obj = reviewer(state["draft"], state["case_notes"])
        failed = [fr.model_dump() for fr in verdict_obj.failed_rules]
        verdict = "pass" if (verdict_obj.verdict == "pass" and not failed) else "revise"
        notes = verdict_obj.notes

        cred_hits = guards.scan_output(state["draft"], cred_patterns)
        if cred_hits:
            verdict = "revise"
            failed = failed + [
                {"rule": "credential_request", "reason": f"Draft requests prohibited info: {cred_hits}"}
            ]
            logger.warning("Output guard forced revise; prohibited info requested: %s", cred_hits)

        logger.info(
            "Round %d review verdict=%s failed_rules=%s",
            state["round"],
            verdict,
            [fr["rule"] for fr in failed],
        )

        record = {
            "round": state["round"],
            "draft": state["draft"],
            "verdict": verdict,
            "failed_rules": failed,
            "notes": notes,
        }
        return {
            "verdict": verdict,
            "feedback": failed,
            "notes": notes,
            "history": state.get("history", []) + [record],
        }

    def route_after_review(state: GraphState) -> str:
        if state["verdict"] == "pass":
            return "approve"
        if state["round"] >= max_rounds:
            return "escalate"
        return "revise"

    def on_approve(state: GraphState) -> None:
        logger.info("Approved -> pending_human_review after %d round(s)", state["round"])

    def on_escalate(state: GraphState) -> None:
        logger.info(
            "Escalated -> human intervention after %d round(s)", len(state.get("history", []))
        )

    return critique_loop(
        GraphState,
        generator=generator_node,
        reviewer=reviewer_node,
        route_after_review=route_after_review,
        input_guard=guard_input_node,
        approved_status="pending_human_review",
        escalated_status="escalated",
        retry_policy=_retry_policy(config.loop.retry),
        on_approve=on_approve,
        on_escalate=on_escalate,
    )
