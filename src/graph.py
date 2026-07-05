from __future__ import annotations

import logging
from functools import partial

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from src import guards
from src.agents import DraftModel, ReviewModel, build_drafter, build_reviewer
from src.config import AppConfig, RetryConfig
from src.policy import apply_review_policy
from src.schemas import FailedRule, GraphState, RoundRecord

logger = logging.getLogger(__name__)

# Channel-write policy (decided, not accidental): `history` uses an
# operator.add reducer (append semantics); `status`/`verdict`/`feedback`/
# `notes` are last-writer-wins, which is safe because this graph is strictly
# sequential. Any future parallel branch must revisit those channels.


def _retry_on(exc: Exception) -> bool:
    """Retry only transient failures.

    Provider SDK errors carry `status_code` (duck-typed, provider-agnostic):
    4xx other than 408/429 is a permanent client/auth error - node retry just
    multiplies the cost of a bad API key. Otherwise mirror LangGraph's default
    exclusions: programming errors and RuntimeError (which covers
    ModelOutputError - absent output is handled by fallback + the service
    boundary, not by re-asking the same model).
    """
    status = getattr(exc, "status_code", None)
    if status is not None and 400 <= status < 500 and status not in (408, 429):
        return False
    # Connection/timeout-shaped errors are transient; checked before the
    # OSError exclusion below (both are OSError subclasses).
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if isinstance(
        exc,
        (
            ValueError,
            TypeError,
            ArithmeticError,
            ImportError,
            LookupError,
            NameError,
            SyntaxError,
            RuntimeError,
            ReferenceError,
            StopIteration,
            StopAsyncIteration,
            OSError,
        ),
    ):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code in (408, 429)
    return True


def _retry_policy(cfg: RetryConfig | None) -> RetryPolicy | None:
    """Map our RetryConfig to LangGraph's built-in RetryPolicy (or None)."""
    if cfg is None:
        return None
    return RetryPolicy(
        max_attempts=cfg.max_attempts,
        backoff_factor=cfg.backoff_factor,
        initial_interval=cfg.initial_interval,
        max_interval=cfg.max_interval,
        jitter=cfg.jitter,
        retry_on=_retry_on,
    )


def initial_state(member_message: str, case_notes: str) -> GraphState:
    return {
        "member_message": member_message,
        "case_notes": case_notes,
        "round": 1,
        "history": [],
    }


def route_after_review(state: GraphState, *, max_rounds: int) -> str:
    if state["verdict"] == "pass":
        return "approve"
    if state["round"] >= max_rounds:
        return "escalate"
    return "revise"


def build_app(
    config: AppConfig,
    drafter_model: DraftModel,
    reviewer_model: ReviewModel,
    drafter_fallback: DraftModel | None = None,
    reviewer_fallback: ReviewModel | None = None,
):
    drafter = build_drafter(drafter_model, config.drafter.system_prompt, drafter_fallback)
    reviewer = build_reviewer(reviewer_model, config.reviewer.system_prompt, reviewer_fallback)
    max_rounds = config.loop.max_rounds
    retry_policy = _retry_policy(config.loop.retry)
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
                    FailedRule(
                        rule="prompt_injection",
                        reason=f"Injection patterns detected: {hits}",
                    )
                ],
                "notes": "Escalated by the input guard before drafting.",
            }
        return {}

    def route_after_guard(state: GraphState) -> str:
        return "escalate" if state.get("status") == "escalated" else "drafter"

    def drafter_node(state: GraphState) -> dict:
        draft = drafter(state["member_message"], state["case_notes"], state.get("feedback"))
        return {"draft": draft}

    def reviewer_node(state: GraphState) -> dict:
        verdict_obj = reviewer(state["draft"], state["case_notes"])
        verdict, failed = apply_review_policy(verdict_obj, state["draft"], cred_patterns)

        logger.info(
            "Round %d review verdict=%s failed_rules=%s",
            state["round"],
            verdict,
            [fr.rule for fr in failed],
        )

        record = RoundRecord(
            round=state["round"],
            draft=state["draft"],
            verdict=verdict,
            failed_rules=failed,
            notes=verdict_obj.notes,
        )
        return {
            "verdict": verdict,
            "feedback": failed,
            "notes": verdict_obj.notes,
            "history": [record],  # the reducer appends
        }

    def increment_node(state: GraphState) -> dict:
        return {"round": state["round"] + 1}

    def approve_node(state: GraphState) -> dict:
        logger.info("Approved -> pending_human_review after %d round(s)", state["round"])
        return {"status": "pending_human_review"}

    def escalate_node(state: GraphState) -> dict:
        logger.info(
            "Escalated -> human intervention after %d round(s)", len(state.get("history", []))
        )
        return {"status": "escalated"}

    g = StateGraph(GraphState)
    g.add_node("guard_input", guard_input_node)
    # The model-calling nodes get LangGraph's built-in node-level retry (when configured).
    g.add_node("drafter", drafter_node, retry_policy=retry_policy)
    g.add_node("reviewer", reviewer_node, retry_policy=retry_policy)
    g.add_node("increment", increment_node)
    g.add_node("approve", approve_node)
    g.add_node("escalate", escalate_node)

    g.add_edge(START, "guard_input")
    g.add_conditional_edges("guard_input", route_after_guard,
                            {"escalate": "escalate", "drafter": "drafter"})
    g.add_edge("drafter", "reviewer")
    g.add_conditional_edges("reviewer", partial(route_after_review, max_rounds=max_rounds),
                            {"approve": "approve", "escalate": "escalate", "revise": "increment"})
    g.add_edge("increment", "drafter")
    g.add_edge("approve", END)
    g.add_edge("escalate", END)
    return g.compile()
