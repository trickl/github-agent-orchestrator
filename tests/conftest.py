"""Test configuration and fixtures."""

from pathlib import Path

import pytest

from github_agent_orchestrator.core.config import (
    GitHubConfig,
    LLMConfig,
    OrchestratorConfig,
    StateConfig,
)


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Provide a temporary state directory."""
    state_dir = tmp_path / ".state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def llm_config() -> LLMConfig:
    """Provide a test LLM configuration."""
    return LLMConfig(
        provider="openai",
        openai_api_key="test-key",
        openai_model="gpt-4",
    )


@pytest.fixture
def github_config() -> GitHubConfig:
    """Provide a test GitHub configuration."""
    return GitHubConfig(
        token="test-token",
        repository="test-owner/test-repo",
    )


@pytest.fixture
def state_config(temp_state_dir: Path) -> StateConfig:
    """Provide a test state configuration."""
    return StateConfig(
        storage_path=temp_state_dir,
        auto_commit=False,
    )


@pytest.fixture
def orchestrator_config(
    llm_config: LLMConfig,
    github_config: GitHubConfig,
    state_config: StateConfig,
) -> OrchestratorConfig:
    """Provide a test orchestrator configuration."""
    return OrchestratorConfig(
        log_level="DEBUG",
        debug=True,
        llm=llm_config,
        github=github_config,
        state=state_config,
    )
