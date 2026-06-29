from __future__ import annotations

from src.config import AppConfig, load_config
from src.graph import build_app, initial_state
from src.core.models import build_model
from src.schemas import RunInput, RunResult


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

    @classmethod
    def from_config_path(cls, config_path: str = "config.yaml") -> "DraftReviewService":
        return cls(load_config(config_path))

    def run(self, member_message: str, case_notes: str) -> RunResult:
        inp = RunInput(member_message=member_message, case_notes=case_notes)
        final = self._app.invoke(initial_state(inp.member_message, inp.case_notes))
        return RunResult.from_state(final)
