from __future__ import annotations

import logging

from src.config import AppConfig, load_config
from src.graph import build_app, initial_state
from src.models import build_model
from src.schemas import FailedRule, ReviewVerdict, RunInput, RunResult

logger = logging.getLogger(__name__)


class DraftReviewService:
    """Composition root: builds the model pipeline + compiled graph ONCE, then
    runs many inputs through it. Construct once (e.g. at app startup) and reuse.

    `drafter_model` / `reviewer_model` default to models built from config; tests
    inject stub models so they run with no API key.
    """

    def __init__(self, config: AppConfig, drafter_model=None, reviewer_model=None):
        drafter_model = drafter_model or build_model(config.drafter)
        reviewer_model = reviewer_model or build_model(config.reviewer)
        drafter_fallback = (
            build_model(config.drafter.fallback) if config.drafter.fallback else None
        )
        reviewer_fallback = (
            build_model(config.reviewer.fallback) if config.reviewer.fallback else None
        )
        self._app = build_app(
            config, drafter_model, reviewer_model, drafter_fallback, reviewer_fallback
        )
        # The full n-round escalate path needs 3n+2 supersteps (measured), which
        # exceeds LangGraph's default limit of 25 from max_rounds=8 up. +4 margin.
        self._recursion_limit = 3 * config.loop.max_rounds + 4

    @classmethod
    def from_config_path(cls, config_path: str = "config.yaml") -> "DraftReviewService":
        return cls(load_config(config_path))

    def run(self, member_message: str, case_notes: str) -> RunResult:
        # Caller-input validation stays OUTSIDE the fail-closed boundary: bad
        # input is the caller's error (422 at the API layer), not a model failure.
        inp = RunInput(member_message=member_message, case_notes=case_notes)
        try:
            final = self._app.invoke(
                initial_state(inp.member_message, inp.case_notes),
                config={"recursion_limit": self._recursion_limit},
            )
        except Exception:
            # Fail closed: every run must end in one of the two promised states.
            # The real error goes to server logs; the caller sees an escalation.
            logger.exception("Agent run failed; escalating (fail closed)")
            return RunResult(
                status="escalated",
                draft=None,
                rounds=0,
                review=ReviewVerdict(
                    verdict="revise",
                    failed_rules=[
                        FailedRule(
                            rule="model_failure",
                            reason="The agent pipeline failed before producing a reviewed draft.",
                        )
                    ],
                    notes="Escalated automatically after a model/runtime failure.",
                ),
                history=[],
            )
        return RunResult.from_state(final)
