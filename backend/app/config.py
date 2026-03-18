"""Configuration for the lightweight local control-plane backend."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings for local control-plane APIs."""

    github_token: str = Field(alias="GITHUB_TOKEN")
    github_api_url: str = Field(default="https://api.github.com", alias="GITHUB_API_URL")
    default_workflow_file: str = Field(
        default="orchestrator.yml", alias="GITHUB_ORCHESTRATOR_WORKFLOW_FILE"
    )
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    orchestrator_cli: str = Field(default="gao", alias="GAO_CLI_COMMAND")
    orchestrator_run_timeout_seconds: int = Field(default=1800, alias="GAO_RUN_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("github_token")
    @classmethod
    def _validate_token(cls, value: str) -> str:
        """Ensure token is non-empty after trimming."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("GITHUB_TOKEN is required")
        return normalized
