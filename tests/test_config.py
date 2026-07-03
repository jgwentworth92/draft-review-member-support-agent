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
    # shipped config has no node retry (opt-in only)
    assert cfg.loop.retry is None

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


# --- startup strictness: typos, bad regexes, empty guards fail the load -----


def test_unknown_top_level_key_rejected(tmp_path: Path):
    import pytest
    with pytest.raises(Exception):
        load_config(_write_config(tmp_path, "loops:\n  max_rounds: 3\n"))


def test_nested_typo_key_rejected(tmp_path: Path):
    # Previously `max_round` was silently ignored and the default ran instead.
    import pytest
    with pytest.raises(Exception):
        load_config(_write_config(tmp_path, "loop:\n  max_round: 5\n"))


def test_invalid_injection_regex_rejected(tmp_path: Path):
    import pytest
    with pytest.raises(Exception, match="injection pattern"):
        load_config(_write_config(tmp_path, 'guards:\n  injection_patterns: ["([unclosed"]\n'))


def test_empty_injection_patterns_rejected(tmp_path: Path):
    # An empty list would silently disable the input guard.
    import pytest
    with pytest.raises(Exception):
        load_config(_write_config(tmp_path, "guards:\n  injection_patterns: []\n"))


def test_empty_yaml_file_rejected(tmp_path: Path):
    import pytest
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError, match="empty or not a YAML mapping"):
        load_config(empty)


# --- fallback resilience inheritance ----------------------------------------


def test_fallback_inherits_timeout_and_max_retries(tmp_path: Path):
    cfg = load_config(_write_config(tmp_path, ""))
    # rebuild drafter with timeout + bare fallback via YAML to exercise load path
    p = tmp_path / "fb.yaml"
    p.write_text(
        "drafter:\n"
        "  provider: anthropic\n"
        "  model: m\n"
        "  system_prompt: draft it\n"
        "  timeout: 30\n"
        "  max_retries: 5\n"
        "  fallback:\n"
        "    provider: anthropic\n"
        "    model: fb\n"
        "reviewer:\n"
        "  provider: anthropic\n"
        "  model: m\n"
        "  system_prompt: review it\n"
    )
    cfg = load_config(p)
    assert cfg.drafter.fallback.timeout == 30
    assert cfg.drafter.fallback.max_retries == 5


def test_fallback_explicit_settings_not_overridden(tmp_path: Path):
    p = tmp_path / "fb2.yaml"
    p.write_text(
        "drafter:\n"
        "  provider: anthropic\n"
        "  model: m\n"
        "  system_prompt: draft it\n"
        "  timeout: 30\n"
        "  fallback:\n"
        "    provider: anthropic\n"
        "    model: fb\n"
        "    timeout: 10\n"
        "    max_retries: 0\n"
        "reviewer:\n"
        "  provider: anthropic\n"
        "  model: m\n"
        "  system_prompt: review it\n"
    )
    cfg = load_config(p)
    assert cfg.drafter.fallback.timeout == 10
    assert cfg.drafter.fallback.max_retries == 0


def test_production_config_ships_timeouts():
    cfg = load_config("config.yaml")
    assert cfg.drafter.timeout is not None
    assert cfg.reviewer.timeout is not None
