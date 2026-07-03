from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src import guards

# extra="forbid" everywhere: a typo'd key (`max_round`, `fallbck`) must be a
# load error, not a silently ignored setting running with defaults.


class ModelConfig(BaseModel):
    """A single LLM endpoint, resolved provider-agnostically via init_chat_model.

    `max_retries` and `timeout` are passed straight through to the provider model:
    the provider SDK retries transient errors (429 / 5xx / overloaded / connection)
    with exponential backoff + jitter.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_retries: int = Field(default=2, ge=0, le=10)
    timeout: Optional[float] = Field(default=None, gt=0)


class AgentConfig(ModelConfig):
    """An agent's primary model plus its prompt and an optional fallback model.

    `fallback` (when set) is wired via LangChain's `Runnable.with_fallbacks()`: if
    the primary model fails, the fallback model/provider is tried.
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    fallback: Optional[ModelConfig] = None

    @model_validator(mode="after")
    def _fallback_inherits_resilience(self) -> "AgentConfig":
        # A bare `fallback:` block must not silently regress to the 600s SDK
        # default timeout (or a different retry budget) than the primary.
        # `temperature` is deliberately not inherited - a fallback may differ.
        if self.fallback is not None:
            if self.fallback.timeout is None:
                self.fallback.timeout = self.timeout
            if "max_retries" not in self.fallback.model_fields_set:
                self.fallback.max_retries = self.max_retries
        return self


class RetryConfig(BaseModel):
    """Node-level retry, mapped to LangGraph's built-in RetryPolicy.

    Applied to the drafter and reviewer nodes. Defaults mirror RetryPolicy.
    """

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_factor: float = Field(default=2.0, ge=1.0)
    initial_interval: float = Field(default=0.5, gt=0)
    max_interval: float = Field(default=128.0, gt=0)
    jitter: bool = True


class LoopConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # le=8 tracks the recursion limit passed by DraftReviewService (3n+4);
    # unvalidated large values crash mid-loop instead of escalating.
    max_rounds: int = Field(default=3, ge=1, le=8)
    retry: Optional[RetryConfig] = None
    # Overall wall-clock deadline per run; on expiry the run fails closed
    # (escalated), it does not hang the caller.
    run_timeout_seconds: float = Field(default=120.0, gt=0)


class GuardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # min_length=1: an empty list silently disables a safety guard; disabling
    # must be an explicit code decision, not a config state.
    injection_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_INJECTION_PATTERNS), min_length=1
    )
    credential_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_CREDENTIAL_PATTERNS), min_length=1
    )

    @field_validator("injection_patterns")
    @classmethod
    def _regexes_compile(cls, patterns: list[str]) -> list[str]:
        # Validate at load: an invalid regex must fail the deploy, not raise
        # per-request inside the graph.
        for p in patterns:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"invalid injection pattern {p!r}: {exc}") from exc
        return patterns


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drafter: AgentConfig
    reviewer: AgentConfig
    loop: LoopConfig = Field(default_factory=LoopConfig)
    guards: GuardConfig = Field(default_factory=GuardConfig)


def load_config(path: str | Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} is empty or not a YAML mapping")
    return AppConfig(**data)
