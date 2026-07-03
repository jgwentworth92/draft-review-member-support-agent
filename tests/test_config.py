from pathlib import Path
from src.config import load_config

def test_load_config_reads_agents_and_loop():
    cfg = load_config("config.yaml")
    assert cfg.drafter.provider == "anthropic"
    assert cfg.drafter.model == "claude-haiku-4-5-20251001"
    assert cfg.reviewer.model == "claude-haiku-4-5-20251001"
    assert cfg.loop.max_rounds == 3
    assert "plain language" in cfg.reviewer.system_prompt.lower()
    # guard defaults are present even though config.yaml omits the section
    assert cfg.guards.injection_patterns
    assert cfg.guards.credential_patterns

def test_missing_required_field_raises(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("drafter:\n  provider: anthropic\n")  # missing model, prompt, reviewer
    import pytest
    with pytest.raises(Exception):
        load_config(bad)


_AGENTS_YAML = """\
drafter:
  provider: anthropic
  model: m
  system_prompt: draft it
reviewer:
  provider: anthropic
  model: m
  system_prompt: review it
"""


def _write_config(tmp_path: Path, extra: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(_AGENTS_YAML + extra)
    return p


def test_max_rounds_zero_rejected(tmp_path: Path):
    import pytest
    with pytest.raises(Exception):
        load_config(_write_config(tmp_path, "loop:\n  max_rounds: 0\n"))


def test_max_rounds_nine_rejected(tmp_path: Path):
    # Values above 8 would exceed the recursion limit budget (3n+4 vs le=8).
    import pytest
    with pytest.raises(Exception):
        load_config(_write_config(tmp_path, "loop:\n  max_rounds: 9\n"))
