from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.core.config import ModelConfig


def build_model(cfg: ModelConfig) -> BaseChatModel:
    """Build a provider-agnostic chat model.

    `max_retries` and `timeout` are standard `init_chat_model` params translated
    per provider; the provider SDK applies exponential backoff + jitter to
    transient errors. `timeout` is only passed when set, so the provider default
    is preserved otherwise.
    """
    kwargs = {
        "model": cfg.model,
        "model_provider": cfg.provider,
        "temperature": cfg.temperature,
        "max_retries": cfg.max_retries,
    }
    if cfg.timeout is not None:
        kwargs["timeout"] = cfg.timeout
    return init_chat_model(**kwargs)
