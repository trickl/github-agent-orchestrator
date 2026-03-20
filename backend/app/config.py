"""Configuration for the lightweight local control-plane backend."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_secret_value(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {'"', "'"}:
        normalized = normalized[1:-1].strip()
    return normalized.replace("\\r\\n", "\n").replace("\\n", "\n")


class Settings(BaseSettings):
    """Environment-backed settings for local control-plane APIs."""

    github_app_id: str = Field(alias="GITHUB_APP_ID")
    github_app_private_key: str = Field(alias="GITHUB_APP_PRIVATE_KEY")
    github_app_installation_id: int | None = Field(default=None, alias="GITHUB_APP_INSTALLATION_ID")
    github_app_slug: str = Field(default="", alias="GITHUB_APP_SLUG")
    github_app_install_url: str = Field(default="", alias="GITHUB_APP_INSTALL_URL")
    github_api_url: str = Field(default="https://api.github.com", alias="GITHUB_API_URL")
    default_workflow_file: str = Field(
        default="orchestrator.yml", alias="GITHUB_ORCHESTRATOR_WORKFLOW_FILE"
    )
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    orchestrator_cli: str = Field(default="gao", alias="GAO_CLI_COMMAND")
    orchestrator_run_timeout_seconds: int = Field(default=1800, alias="GAO_RUN_TIMEOUT_SECONDS")

    backend_require_auth: bool = Field(default=True, alias="BACKEND_REQUIRE_AUTH")
    github_oauth_client_id: str = Field(default="", alias="GITHUB_OAUTH_CLIENT_ID")
    github_oauth_client_secret: str = Field(default="", alias="GITHUB_OAUTH_CLIENT_SECRET")
    github_oauth_redirect_uri: str = Field(default="", alias="GITHUB_OAUTH_REDIRECT_URI")
    auth_frontend_redirect_url: str = Field(
        default="https://trickl.github.io/github-agent-orchestrator/",
        alias="AUTH_FRONTEND_REDIRECT_URL",
    )
    auth_session_secret: str = Field(default="", alias="AUTH_SESSION_SECRET")
    auth_allowed_github_users: str = Field(default="", alias="AUTH_ALLOWED_GITHUB_USERS")
    auth_session_max_age_seconds: int = Field(default=604800, alias="AUTH_SESSION_MAX_AGE_SECONDS")
    auth_cookie_secure: bool = Field(default=True, alias="AUTH_COOKIE_SECURE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("github_app_id")
    @classmethod
    def _validate_app_id(cls, value: str) -> str:
        """Ensure app id is non-empty after trimming."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("GITHUB_APP_ID is required")
        return normalized

    @field_validator("github_app_private_key")
    @classmethod
    def _validate_private_key(cls, value: str) -> str:
        """Ensure app private key is non-empty after trimming."""
        normalized = _normalize_secret_value(value)
        if not normalized:
            raise ValueError("GITHUB_APP_PRIVATE_KEY is required")
        if "BEGIN" not in normalized or "PRIVATE KEY" not in normalized:
            raise ValueError(
                "GITHUB_APP_PRIVATE_KEY must be a PEM private key (including BEGIN/END PRIVATE KEY)"
            )
        return normalized

    @model_validator(mode="after")
    def _validate_auth_dependencies(self) -> "Settings":
        if not self.backend_require_auth:
            return self

        required = {
            "GITHUB_OAUTH_CLIENT_ID": self.github_oauth_client_id,
            "GITHUB_OAUTH_CLIENT_SECRET": self.github_oauth_client_secret,
            "GITHUB_OAUTH_REDIRECT_URI": self.github_oauth_redirect_uri,
            "AUTH_SESSION_SECRET": self.auth_session_secret,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "Missing required auth settings when BACKEND_REQUIRE_AUTH=true: "
                + ", ".join(missing)
            )
        return self
