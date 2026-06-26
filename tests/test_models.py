from unittest.mock import patch
from src.config import AgentConfig
from src.models import build_model

def test_build_model_passes_config_to_init_chat_model():
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001",
                      temperature=0.3, system_prompt="x")
    with patch("src.models.init_chat_model") as mock_init:
        mock_init.return_value = "MODEL"
        result = build_model(cfg)
    mock_init.assert_called_once_with(
        model="claude-haiku-4-5-20251001",
        model_provider="anthropic",
        temperature=0.3,
        max_retries=2,
    )
    assert result == "MODEL"
