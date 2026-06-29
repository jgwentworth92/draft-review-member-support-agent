from __future__ import annotations

from pathlib import Path

from src.core.models import build_model
from src.core.service import PipelineService
from src.scenarios.quality.config import AppConfig, load_config
from src.scenarios.quality.graph import build_app, initial_state
from src.scenarios.quality.schemas import RunInput, RunResult


class QualityService(PipelineService):
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
        graph = build_app(
            config, drafter_model, reviewer_model, drafter_fallback, reviewer_fallback
        )
        super().__init__(graph)

    @classmethod
    def from_config_path(cls, path: str | None = None) -> "QualityService":
        path = path or str(Path(__file__).with_name("config.yaml"))
        return cls(load_config(path))

    def run(self, member_message: str, case_notes: str) -> RunResult:
        inp = RunInput(member_message=member_message, case_notes=case_notes)
        final = self.invoke(initial_state(inp.member_message, inp.case_notes))
        return RunResult.from_state(final)


DraftReviewService = QualityService
