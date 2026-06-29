from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.core.config import AgentConfig, GuardConfig, LoopConfig


class AppConfig(BaseModel):
    drafter: AgentConfig
    reviewer: AgentConfig
    loop: LoopConfig = Field(default_factory=LoopConfig)
    guards: GuardConfig = Field(default_factory=GuardConfig)


def load_config(path: str | Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)
