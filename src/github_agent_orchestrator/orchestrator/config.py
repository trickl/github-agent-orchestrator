"""Configuration for the local-first orchestrator.

This module intentionally stays minimal for Phase 1/1A.

Configuration is loaded from:
- environment variables
- and a local `.env` file (if present)

To avoid collisions with other tools that may also use `GITHUB_TOKEN`, this
project uses a dedicated token variable: `ORCHESTRATOR_GITHUB_TOKEN`.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Settings for the local orchestrator.

    Environment variables:
    - ORCHESTRATOR_GITHUB_TOKEN
    - GITHUB_BASE_URL   (optional)
    - LOG_LEVEL         (optional)

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
    require_github_token: bool = Field(
        default=True,
        exclude=True,
        description="Internal flag to allow bootstrap commands without a token.",
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

    copilot_assignee: str = Field(
        default="copilot-swe-agent[bot]",
        validation_alias="COPILOT_ASSIGNEE",
        description=(
            "GitHub login used for Copilot coding agent issue assignment. "
            "The current documented default is 'copilot-swe-agent[bot]'. "
            "Override via COPILOT_ASSIGNEE if your org uses a different login."
        ),
    )

    target_base_branch: str = Field(
        default="",
        validation_alias="ORCHESTRATOR_TARGET_BASE_BRANCH",
        description=(
            "Optional explicit base branch for Copilot work in the target repo. "
            "If empty, the repository default branch is used."
        ),
    )

    create_work_branch: bool = Field(
        default=True,
        validation_alias="ORCHESTRATOR_CREATE_WORK_BRANCH",
        description=(
            "If true, create a dedicated work branch per issue (derived from the base branch) and "
            "assign Copilot to work against that branch."
        ),
    )

    work_branch_prefix: str = Field(
        default="orchestrator/work",
        validation_alias="ORCHESTRATOR_WORK_BRANCH_PREFIX",
        description="Prefix used when creating per-issue work branches.",
    )

    premium_request_cost_usd: float = Field(
        default=0.04,
        validation_alias="ORCHESTRATOR_PREMIUM_REQUEST_COST_USD",
        description="Conservative cost per premium request (USD).",
        ge=0.0,
    )

    estimated_premium_requests_per_pr: int = Field(
        default=1,
        validation_alias="ORCHESTRATOR_ESTIMATED_PREMIUM_REQUESTS_PER_PR",
        description="Conservative estimate of premium requests per PR.",
        ge=0,
    )

    estimated_prs_per_iteration: int = Field(
        default=3,
        validation_alias="ORCHESTRATOR_ESTIMATED_PRS_PER_ITERATION",
        description="Conservative estimate of PRs per iteration.",
        ge=0,
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _require_github_auth(self) -> OrchestratorSettings:
        if self.require_github_token and not self.github_token.strip():
            raise ValueError("ORCHESTRATOR_GITHUB_TOKEN is required")
        return self
