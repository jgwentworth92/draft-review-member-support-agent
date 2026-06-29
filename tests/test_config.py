from pathlib import Path
from src.scenarios.quality.config import load_config

def test_load_config_reads_agents_and_loop():
    cfg = load_config("src/scenarios/quality/config.yaml")
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
