from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.config import AgentConfig


def build_model(cfg: AgentConfig) -> BaseChatModel:
    return init_chat_model(
        model=cfg.model,
        model_provider=cfg.provider,
        temperature=cfg.temperature,
    )
