from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from src.config import AppConfig, load_config
from src.graph import build_app, initial_state
from src.models import build_model
from src.schemas import FailedRule, ReviewVerdict, RunInput, RunResult

logger = logging.getLogger(__name__)


class RunDeadlineExceeded(RuntimeError):
    """The overall run deadline (loop.run_timeout_seconds) expired."""


class DraftReviewService:
    """Composition root: builds the model pipeline + compiled graph ONCE, then
    runs many inputs through it. Construct once (e.g. at app startup) and reuse.

    `drafter_model` / `reviewer_model` default to models built from config; tests
    inject stub models so they run with no API key.
    """

    def __init__(
        self,
        config: AppConfig,
        drafter_model=None,
        reviewer_model=None,
        drafter_fallback=None,
        reviewer_fallback=None,
    ):
        drafter_model = drafter_model or build_model(config.drafter)
        reviewer_model = reviewer_model or build_model(config.reviewer)
        # Injected fallbacks (tests) win; otherwise build from config when set.
        if drafter_fallback is None and config.drafter.fallback:
            drafter_fallback = build_model(config.drafter.fallback)
        if reviewer_fallback is None and config.reviewer.fallback:
            reviewer_fallback = build_model(config.reviewer.fallback)
        self._app = build_app(
            config, drafter_model, reviewer_model, drafter_fallback, reviewer_fallback
        )
        # The full n-round escalate path needs 3n+2 supersteps (measured), which
        # exceeds LangGraph's default limit of 25 from max_rounds=8 up. +4 margin.
        self._recursion_limit = 3 * config.loop.max_rounds + 4
        self._run_timeout = config.loop.run_timeout_seconds

    @classmethod
    def from_config_path(cls, config_path: str = "config.yaml") -> "DraftReviewService":
        return cls(load_config(config_path))

    def run(self, member_message: str, case_notes: str) -> RunResult:
        # Caller-input validation stays OUTSIDE the fail-closed boundary: bad
        # input is the caller's error (422 at the API layer), not a model failure.
        inp = RunInput(member_message=member_message, case_notes=case_notes)
        try:
            final = self._invoke_with_deadline(inp)
        except RunDeadlineExceeded:
            logger.exception("Agent run exceeded deadline; escalating (fail closed)")
            return self._escalated_result(
                f"The run exceeded its {self._run_timeout}s deadline."
            )
        except Exception:
            # Fail closed: every run must end in one of the two promised states.
            # The real error goes to server logs; the caller sees an escalation.
            logger.exception("Agent run failed; escalating (fail closed)")
            return self._escalated_result(
                "The agent pipeline failed before producing a reviewed draft."
            )
        return RunResult.from_state(final)

    def _invoke_with_deadline(self, inp: RunInput) -> dict:
        # Per-call executor: with a shared single worker, one hung run would
        # queue healthy runs behind it. The worker thread cannot be killed on
        # timeout - it runs to completion in the background, bounded by the
        # per-request SDK timeouts configured on the models.
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self._app.invoke,
                initial_state(inp.member_message, inp.case_notes),
                config={"recursion_limit": self._recursion_limit},
            )
            try:
                return future.result(timeout=self._run_timeout)
            except FuturesTimeoutError:
                raise RunDeadlineExceeded(
                    f"run exceeded {self._run_timeout}s deadline"
                ) from None
        finally:
            executor.shutdown(wait=False)

    @staticmethod
    def _escalated_result(reason: str) -> RunResult:
        return RunResult(
            status="escalated",
            draft=None,
            rounds=0,
            review=ReviewVerdict(
                verdict="revise",
                failed_rules=[FailedRule(rule="model_failure", reason=reason)],
                notes="Escalated automatically after a model/runtime failure.",
            ),
            history=[],
        )
