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

    agent_state_path: Path = Field(default=Path("agent_state"), validation_alias="AGENT_STATE_PATH")
    planning_root: Path = Field(
        default=Path("planning"), validation_alias="ORCHESTRATOR_PLANNING_ROOT"
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

    @property
    def issues_state_file(self) -> Path:
        return self.agent_state_path / "issues.json"

    @property
    def jobs_state_file(self) -> Path:
        return self.agent_state_path / "jobs.json"

    @property
    def timeline_state_file(self) -> Path:
        return self.agent_state_path / "timeline.json"

    @property
    def cognitive_tasks_state_file(self) -> Path:
        # Keep cognitive tasks next to other planning state.
        return self.planning_root / "state" / "cognitive_tasks.json"

    @property
    def legacy_generation_rules_state_file(self) -> Path:
        # Backwards-compatible location used by older dashboard versions.
        return self.planning_root / "state" / "generation_rules.json"

    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
