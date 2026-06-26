from __future__ import annotations

from langchain_core.messages import AIMessage


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
