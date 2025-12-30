"""Unit tests for configuration."""

from github_agent_orchestrator.core.config import (
    GitHubConfig,
    LLMConfig,
    OrchestratorConfig,
    StateConfig,
)


def test_llm_config_defaults() -> None:
    """Test LLM config default values."""
    config = LLMConfig(openai_api_key="test-key")

    assert config.provider == "openai"
    assert config.openai_model == "gpt-4"
    assert config.openai_temperature == 0.7
    assert config.llama_n_ctx == 4096


def test_github_config_defaults() -> None:
    """Test GitHub config default values."""
    config = GitHubConfig(token="test-token", repository="owner/repo")

    assert config.token == "test-token"
    assert config.repository == "owner/repo"
    assert config.base_url == "https://api.github.com"


def test_state_config_defaults() -> None:
    """Test state config default values."""
    config = StateConfig()

    assert config.auto_commit is True
    assert config.state_branch == "orchestrator-state"


def test_orchestrator_config_composition() -> None:
    """Test orchestrator config with nested configs."""
    config = OrchestratorConfig(
        log_level="DEBUG",
        debug=True,
    )

    assert config.log_level == "DEBUG"
    assert config.debug is True
    assert isinstance(config.llm, LLMConfig)
    assert isinstance(config.github, GitHubConfig)
    assert isinstance(config.state, StateConfig)
