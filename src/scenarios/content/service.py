from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel
from src.core.config import AgentConfig
from src.core.models import build_model
from src.core.service import PipelineService
from src.scenarios.content.graph import build_app, initial_state
from src.scenarios.content.schemas import ContentResult


class ContentConfig(BaseModel):
    researcher: AgentConfig
    writer: AgentConfig


class ContentService(PipelineService):
    def __init__(self, config: ContentConfig, researcher_model=None, writer_model=None):
        researcher_model = researcher_model or build_model(config.researcher)
        writer_model = writer_model or build_model(config.writer)
        super().__init__(build_app(config, researcher_model, writer_model))

    @classmethod
    def from_config_path(cls, path: str = "src/scenarios/content/config.yaml"):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(ContentConfig(**data))

    @classmethod
    def from_models(cls, researcher_model, writer_model):
        cfg = ContentConfig(
            researcher=AgentConfig(provider="anthropic", model="stub", system_prompt="R"),
            writer=AgentConfig(provider="anthropic", model="stub", system_prompt="W"),
        )
        return cls(cfg, researcher_model, writer_model)

    def run(self, product_name: str, spec_sheet: str) -> ContentResult:
        final = self.invoke(initial_state(product_name, spec_sheet))
        return ContentResult.from_state(final)
