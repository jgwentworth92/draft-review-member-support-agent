from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel
from src.core.config import AgentConfig
from src.core.models import build_model
from src.core.service import PipelineService
from src.scenarios.policy.graph import build_app, initial_state
from src.scenarios.policy.schemas import PolicyResult


class PolicyConfig(BaseModel):
    retriever: AgentConfig
    responder: AgentConfig


class PolicyService(PipelineService):
    def __init__(self, config: PolicyConfig, retriever_model=None, responder_model=None):
        retriever_model = retriever_model or build_model(config.retriever)
        responder_model = responder_model or build_model(config.responder)
        super().__init__(build_app(config, retriever_model, responder_model))

    @classmethod
    def from_config_path(cls, path: str = "src/scenarios/policy/config.yaml"):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(PolicyConfig(**data))

    @classmethod
    def from_models(cls, retriever_model, responder_model):
        cfg = PolicyConfig(
            retriever=AgentConfig(provider="anthropic", model="stub", system_prompt="R"),
            responder=AgentConfig(provider="anthropic", model="stub", system_prompt="W"),
        )
        return cls(cfg, retriever_model, responder_model)

    def run(self, question: str, handbook: str) -> PolicyResult:
        final = self.invoke(initial_state(question, handbook))
        return PolicyResult.from_state(final)
