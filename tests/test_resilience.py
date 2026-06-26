"""Resilience layer: provider retries/timeout, LangChain fallbacks, LangGraph node retry.

These exercise the BUILT-IN mechanisms we wired (not custom retry logic):
- `build_model` forwards `max_retries`/`timeout` to `init_chat_model` (provider SDK
  exponential backoff).
- `build_drafter`/`build_reviewer` use `Runnable.with_fallbacks(...)` so a failing
  primary falls over to a secondary model.
- `build_app` attaches LangGraph's `RetryPolicy` to the model nodes so a transient
  node failure is retried.
"""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.config import ModelConfig, RetryConfig, load_config
from src.agents import build_drafter, build_reviewer
from src.graph import build_app, initial_state
from src.models import build_model
from src.schemas import ReviewVerdict
from tests.stub_model import ScriptedModel


# --- provider-level retries / timeout (init_chat_model passthrough) ---------


def test_build_model_passes_max_retries_and_timeout_when_set():
    cfg = ModelConfig(provider="anthropic", model="m", temperature=0.0, max_retries=5, timeout=30.0)
    with patch("src.models.init_chat_model") as mk:
        build_model(cfg)
    mk.assert_called_once_with(
        model="m", model_provider="anthropic", temperature=0.0, max_retries=5, timeout=30.0
    )


def test_build_model_omits_timeout_when_none():
    cfg = ModelConfig(provider="anthropic", model="m")
    with patch("src.models.init_chat_model") as mk:
        build_model(cfg)
    _, kwargs = mk.call_args
    assert "timeout" not in kwargs
    assert kwargs["max_retries"] == 2


# --- LangChain with_fallbacks (drafter + reviewer) -------------------------


def _boom(_):
    raise RuntimeError("primary model unavailable")


def test_drafter_falls_back_when_primary_fails():
    primary = RunnableLambda(_boom)
    fallback = RunnableLambda(lambda _messages: AIMessage(content="fallback draft body"))
    draft = build_drafter(primary, "system", fallback_model=fallback)
    assert draft("member message", "case notes", None) == "fallback draft body"


class _StructuredModel:
    """Minimal stand-in exposing `.with_structured_output()` like a chat model."""

    def __init__(self, runner):
        self._runner = runner

    def with_structured_output(self, _schema):
        return self._runner


def test_reviewer_falls_back_when_primary_fails():
    primary = _StructuredModel(RunnableLambda(_boom))
    fallback = _StructuredModel(RunnableLambda(lambda _messages: ReviewVerdict(verdict="pass")))
    review = build_reviewer(primary, "system", fallback_model=fallback)
    assert review("draft", "notes").verdict == "pass"


# --- LangGraph RetryPolicy (node-level retry) ------------------------------


class _FailOnceReviewer:
    """Reviewer model whose structured runner raises on the first call, then passes."""

    def __init__(self):
        self.calls = 0

    def with_structured_output(self, _schema):
        outer = self

        class _Runner:
            def invoke(self, _messages):
                outer.calls += 1
                if outer.calls == 1:
                    raise Exception("transient model error")
                return ReviewVerdict(verdict="pass")

        return _Runner()


def test_node_retry_recovers_from_transient_failure():
    cfg = load_config("config.yaml")
    # Enable LangGraph node retry with near-zero backoff so the test is fast.
    cfg.loop.retry = RetryConfig(max_attempts=2, initial_interval=0.01, max_interval=0.02)

    reviewer = _FailOnceReviewer()
    app = build_app(
        cfg,
        ScriptedModel(draft_responses=["A compliant draft. Please confirm the last 4 digits."]),
        reviewer,
    )
    final = app.invoke(initial_state("member message", "case notes"))

    assert reviewer.calls == 2  # failed once, retried, then succeeded
    assert final["status"] == "pending_human_review"
    assert len(final["history"]) == 1


def test_no_retry_policy_by_default():
    # Default config has no loop.retry; a single transient failure is NOT retried.
    cfg = load_config("config.yaml")
    assert cfg.loop.retry is None
