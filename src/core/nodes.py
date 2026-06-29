from __future__ import annotations
from typing import Callable, Type
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel


def text_agent_node(model, system_prompt: str, format_fn: Callable[..., str], fallback=None) -> Callable[..., str]:
    runnable = model if fallback is None else model.with_fallbacks([fallback])

    def call(*args, **kwargs) -> str:
        human = format_fn(*args, **kwargs)
        message = runnable.invoke([SystemMessage(system_prompt), HumanMessage(human)])
        return message.content
    return call


def structured_agent_node(
    model, schema: Type[BaseModel], system_prompt: str, format_fn: Callable[..., str], fallback=None
) -> Callable[..., BaseModel]:
    structured = model.with_structured_output(schema)
    if fallback is not None:
        structured = structured.with_fallbacks([fallback.with_structured_output(schema)])

    def call(*args, **kwargs) -> BaseModel:
        human = format_fn(*args, **kwargs)
        return structured.invoke([SystemMessage(system_prompt), HumanMessage(human)])
    return call
