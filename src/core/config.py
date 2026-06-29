from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.core import guards


class ModelConfig(BaseModel):
    """A single LLM endpoint, resolved provider-agnostically via init_chat_model.

    `max_retries` and `timeout` are passed straight through to the provider model:
    the provider SDK retries transient errors (429 / 5xx / overloaded / connection)
    with exponential backoff + jitter.
    """

    provider: str
    model: str
    temperature: float = 0.0
    max_retries: int = 2
    timeout: Optional[float] = None


class AgentConfig(ModelConfig):
    """An agent's primary model plus its prompt and an optional fallback model.

    `fallback` (when set) is wired via LangChain's `Runnable.with_fallbacks()`: if
    the primary model fails, the fallback model/provider is tried.
    """

    system_prompt: str
    fallback: Optional[ModelConfig] = None


class RetryConfig(BaseModel):
    """Node-level retry, mapped to LangGraph's built-in RetryPolicy.

    Applied to the drafter and reviewer nodes. Defaults mirror RetryPolicy.
    """

    max_attempts: int = 3
    backoff_factor: float = 2.0
    initial_interval: float = 0.5
    max_interval: float = 128.0
    jitter: bool = True


class LoopConfig(BaseModel):
    max_rounds: int = 3
    retry: Optional[RetryConfig] = None


class GuardConfig(BaseModel):
    injection_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_INJECTION_PATTERNS)
    )
    credential_patterns: list[str] = Field(
        default_factory=lambda: list(guards.DEFAULT_CREDENTIAL_PATTERNS)
    )
