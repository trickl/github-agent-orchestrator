"""Configuration for the local-first orchestrator.

This module intentionally stays minimal for Phase 1/1A.

Configuration is loaded from:
- environment variables
- and a local `.env` file (if present)

To avoid collisions with other tools that may also use `GITHUB_TOKEN`, this
project uses a dedicated token variable: `ORCHESTRATOR_GITHUB_TOKEN`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Settings for the local orchestrator.

    Environment variables:
    - ORCHESTRATOR_GITHUB_TOKEN
    - GITHUB_BASE_URL   (optional)
    - LOG_LEVEL         (optional)
    - AGENT_STATE_PATH  (optional)

    Notes:
        Pydantic-settings supports overriding the env file in tests via:
        `OrchestratorSettings(_env_file=path_to_env)`.
    """

    # Defaults are intentionally empty, but validation below enforces that values are provided
    # (typically via `.env`). This keeps mypy happy with `OrchestratorSettings()`.
    github_token: str = Field(
        default="",
        validation_alias="ORCHESTRATOR_GITHUB_TOKEN",
        description="GitHub token used for API authentication",
    )
    github_base_url: str = Field(
        default="https://api.github.com",
        validation_alias="GITHUB_BASE_URL",
        description="GitHub API base URL (useful for GitHub Enterprise)",
    )

    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Root logging level",
    )

    agent_state_path: Path = Field(
        default=Path("agent_state"),
        validation_alias="AGENT_STATE_PATH",
        description="Directory where local agent state is persisted",
    )

    workflow_state_path: Path = Field(
        default=Path("workflow/state.json"),
        validation_alias="ORCHESTRATOR_WORKFLOW_STATE_PATH",
        description="Path where the workflow state machine is persisted",
    )

    copilot_assignee: str = Field(
        default="copilot-swe-agent[bot]",
        validation_alias="COPILOT_ASSIGNEE",
        description=(
            "GitHub login used for Copilot coding agent issue assignment. "
            "The current documented default is 'copilot-swe-agent[bot]'. "
            "Override via COPILOT_ASSIGNEE if your org uses a different login."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _require_github_auth(self) -> OrchestratorSettings:
        if not self.github_token.strip():
            raise ValueError("ORCHESTRATOR_GITHUB_TOKEN is required")
        return self

    @property
    def issues_state_file(self) -> Path:
        """Path where created issue metadata is persisted."""

        return self.agent_state_path / "issues.json"

    @property
    def workflow_state_file(self) -> Path:
        """Path where workflow state is persisted."""

        return self.workflow_state_path
