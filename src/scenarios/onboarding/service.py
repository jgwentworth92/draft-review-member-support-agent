from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel
from src.core.config import AgentConfig
from src.core.models import build_model
from src.core.service import PipelineService
from src.scenarios.onboarding.graph import build_app, initial_state
from src.scenarios.onboarding.schemas import OnboardingResult


class OnboardingConfig(BaseModel):
    planner: AgentConfig
    executor: AgentConfig


class OnboardingService(PipelineService):
    def __init__(self, config: OnboardingConfig, planner_model=None, executor_model=None):
        planner_model = planner_model or build_model(config.planner)
        executor_model = executor_model or build_model(config.executor)
        super().__init__(build_app(config, planner_model, executor_model))

    @classmethod
    def from_config_path(cls, path: str = "src/scenarios/onboarding/config.yaml"):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(OnboardingConfig(**data))

    @classmethod
    def from_models(cls, planner_model, executor_model):
        cfg = OnboardingConfig(
            planner=AgentConfig(provider="anthropic", model="stub", system_prompt="P"),
            executor=AgentConfig(provider="anthropic", model="stub", system_prompt="E"),
        )
        return cls(cfg, planner_model, executor_model)

    def run(self, request: str, role: str) -> OnboardingResult:
        final = self.invoke(initial_state(request, role))
        return OnboardingResult.from_state(final)
