from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src import guards


class AgentConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    system_prompt: str


class LoopConfig(BaseModel):
    max_rounds: int = 3


class GuardConfig(BaseModel):
    injection_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_INJECTION_PATTERNS)
    )
    credential_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_CREDENTIAL_PATTERNS)
    )


class AppConfig(BaseModel):
    drafter: AgentConfig
    reviewer: AgentConfig
    loop: LoopConfig = Field(default_factory=LoopConfig)
    guards: GuardConfig = Field(default_factory=GuardConfig)


def load_config(path: str | Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)
