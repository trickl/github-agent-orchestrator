"""Configuration for the REST server.

This server is intentionally "local-first": it can start and serve the UI even if
no GitHub token is configured. Endpoints that require GitHub access must validate
credentials at request time.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Settings for the REST API + UI hosting.

    Notes:
        - Unlike :class:`github_agent_orchestrator.orchestrator.config.OrchestratorSettings`,
          this does NOT require a GitHub token at startup. This keeps the dashboard usable
          against local state (planning docs, issue queue) without external credentials.
    """

    github_token: str = Field(default="", validation_alias="ORCHESTRATOR_GITHUB_TOKEN")
    github_base_url: str = Field(
        default="https://api.github.com", validation_alias="GITHUB_BASE_URL"
    )

    copilot_assignee: str = Field(
        default="copilot-swe-agent[bot]",
        validation_alias="COPILOT_ASSIGNEE",
        description=(
            "GitHub login used for Copilot coding agent issue assignment. "
            "Override via COPILOT_ASSIGNEE if your org uses a different login."
        ),
    )

    auto_promote_enabled: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_AUTO_PROMOTE_ENABLED",
        description=(
            "If true, the server will periodically attempt Step B promotion (pending file -> issue -> assign)."
        ),
    )
    auto_promote_interval_seconds: float = Field(
        default=30.0,
        validation_alias="ORCHESTRATOR_AUTO_PROMOTE_INTERVAL_SECONDS",
        description="Polling interval (seconds) for auto promotion when enabled.",
    )

    # Active repository context for the dashboard. If set, issue lists and overview
    # will be scoped to this repo by default.
    default_repo: str = Field(default="", validation_alias="ORCHESTRATOR_DEFAULT_REPO")

    # Where the Vite build output lives when serving the UI from the backend.
    ui_dist_path: Path = Field(default=Path("ui/dist"), validation_alias="ORCHESTRATOR_UI_DIST")

    # Dev-friendly CORS (Vite). Override via ORCHESTRATOR_CORS_ORIGINS=...
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="ORCHESTRATOR_CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins.",
    )

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
