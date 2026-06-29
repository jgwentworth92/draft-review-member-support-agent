from __future__ import annotations

from langchain_core.messages import AIMessage


class StubModel:
    """Generic test double for a chat model used by the core node factories and
    scenario pipelines. Returns a fixed `reply` from .invoke() and a fixed
    `structured` object from .with_structured_output(...).invoke(). Records the
    last HumanMessage content as `last_human`."""

    def __init__(self, reply=None, structured=None):
        self._reply = reply
        self._structured = structured
        self.last_human = None

    def invoke(self, messages):
        self.last_human = messages[-1].content
        return AIMessage(content=self._reply)

    def with_structured_output(self, schema):
        return _StubStructuredRunner(self)

    def with_fallbacks(self, fallbacks):
        return self


class _StubStructuredRunner:
    def __init__(self, parent):
        self._parent = parent

    def invoke(self, messages):
        self._parent.last_human = messages[-1].content
        return self._parent._structured

    def with_fallbacks(self, fallbacks):
        return self


class _StructuredRunner:
    def __init__(self, parent: "ScriptedModel"):
        self._parent = parent

    def invoke(self, messages):
        if not self._parent._reviews:
            raise AssertionError("ScriptedModel ran out of review responses")
        return self._parent._reviews.pop(0)


class ScriptedModel:
    """Test double standing in for a LangChain chat model.

    Implements only the surface the agents use: `.invoke()` (drafter) and
    `.with_structured_output().invoke()` (reviewer).
    """

    def __init__(self, draft_responses=None, review_responses=None):
        self._drafts = list(draft_responses or [])
        self._reviews = list(review_responses or [])

    def invoke(self, messages):
        if not self._drafts:
            raise AssertionError("ScriptedModel ran out of draft responses")
        return AIMessage(content=self._drafts.pop(0))

    def with_structured_output(self, schema):
        return _StructuredRunner(self)
