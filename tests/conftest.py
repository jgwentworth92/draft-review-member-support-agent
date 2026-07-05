"""Shared deterministic-test fixtures.

make_test_config builds an AppConfig in code, pinned independently of the
production config.yaml: a legitimate production change (max_rounds, guard
overrides, timeouts) must not break unit tests. Only tests/test_config.py
loads the real file - that is the deliberate "production file parses under
the strict schema" gate.
"""

from __future__ import annotations

from src.config import AgentConfig, AppConfig, GuardConfig, LoopConfig


def make_test_config(max_rounds: int = 3, **loop_overrides) -> AppConfig:
    return AppConfig(
        drafter=AgentConfig(
            provider="anthropic",
            model="test-drafter",
            system_prompt="Draft a reply email body.",
        ),
        reviewer=AgentConfig(
            provider="anthropic",
            model="test-reviewer",
            system_prompt="Review the draft against the checklist.",
        ),
        loop=LoopConfig(
            max_rounds=max_rounds,
            # Generous so CI never trips the deadline unless a test opts in.
            run_timeout_seconds=loop_overrides.pop("run_timeout_seconds", 30.0),
            **loop_overrides,
        ),
        guards=GuardConfig(),
    )
