"""Core configuration for the orchestrator."""

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """Configuration for LLM providers."""

    provider: Literal["openai", "llama"] = Field(
        default="openai",
        description="LLM provider to use",
    )

    # OpenAI settings
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )
    openai_model: str = Field(
        default="gpt-4",
        description="OpenAI model to use",
    )
    openai_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for OpenAI model",
    )

    # LLaMA settings
    llama_model_path: Path | None = Field(
        default=None,
        description="Path to LLaMA model file",
    )
    llama_n_ctx: int = Field(
        default=4096,
        gt=0,
        description="Context window size for LLaMA",
    )
    llama_n_threads: int | None = Field(
        default=None,
        description="Number of threads for LLaMA (None = auto)",
    )

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_LLM_",
        env_file=".env",
        extra="ignore",
    )


class GitHubConfig(BaseSettings):
    """Configuration for GitHub integration."""

    token: str | None = Field(
        default=None,
        description="GitHub personal access token",
    )
    repository: str | None = Field(
        default=None,
        description="Repository in format 'owner/repo'",
    )
    base_url: str = Field(
        default="https://api.github.com",
        description="GitHub API base URL",
    )

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_GITHUB_",
        env_file=".env",
        extra="ignore",
    )


class StateConfig(BaseSettings):
    """Configuration for state management."""

    storage_path: Path = Field(
        default=Path(".state"),
        description="Path to store persistent state",
    )
    auto_commit: bool = Field(
        default=True,
        description="Automatically commit state changes",
    )
    state_branch: str = Field(
        default="orchestrator-state",
        description="Branch name for state storage",
    )

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_STATE_",
        env_file=".env",
        extra="ignore",
    )


class OrchestratorConfig(BaseSettings):
    """Main configuration for the orchestrator."""

    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM configuration",
    )
    github: GitHubConfig = Field(
        default_factory=GitHubConfig,
        description="GitHub configuration",
    )
    state: StateConfig = Field(
        default_factory=StateConfig,
        description="State configuration",
    )

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        env_file=".env",
        extra="ignore",
    )

    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if self.debug:
            logging.getLogger("github_agent_orchestrator").setLevel(logging.DEBUG)
