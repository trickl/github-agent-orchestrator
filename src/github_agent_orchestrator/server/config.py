"""Configuration for the REST server.

This server is intentionally "local-first": it can start and serve the UI even if
no GitHub token is configured. Endpoints that require GitHub access must validate
credentials at request time.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
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

    prune_non_copilot_assignees: bool = Field(
        default=True,
        validation_alias="ORCHESTRATOR_PRUNE_NON_COPILOT_ASSIGNEES",
        description=(
            "If true, remove non-Copilot assignees when assigning issues unless the issue has an "
            "allowed label (see ORCHESTRATOR_NON_COPILOT_ASSIGNEE_LABELS)."
        ),
    )

    non_copilot_assignee_labels: str = Field(
        default="Development",
        validation_alias="ORCHESTRATOR_NON_COPILOT_ASSIGNEE_LABELS",
        description=(
            "Comma-separated labels for which non-Copilot assignees should be preserved."
        ),
    )

    include_copilot_job_errors: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_INCLUDE_COPILOT_JOB_ERRORS",
        description=(
            "If true, the loop status will attempt to surface the latest Copilot job failure "
            "details (requires a token with actions:read)."
        ),
    )

    copilot_job_error_max_lines: int = Field(
        default=5,
        validation_alias="ORCHESTRATOR_COPILOT_JOB_ERROR_MAX_LINES",
        description="Maximum number of error lines to surface from Copilot job logs.",
        ge=1,
        le=20,
    )

    copilot_job_error_log_max_bytes: int = Field(
        default=2_000_000,
        validation_alias="ORCHESTRATOR_COPILOT_JOB_ERROR_LOG_MAX_BYTES",
        description=(
            "Maximum number of bytes to download for Copilot job logs while extracting error "
            "snippets. Larger logs are skipped to protect server memory."
        ),
        ge=64 * 1024,
        le=50_000_000,
    )

    copilot_job_error_scan_max_lines: int = Field(
        default=4000,
        validation_alias="ORCHESTRATOR_COPILOT_JOB_ERROR_SCAN_MAX_LINES",
        description=(
            "Maximum number of log lines retained in-memory while scanning Copilot job logs "
            "for error snippets."
        ),
        ge=100,
        le=100_000,
    )

    auto_promote_enabled: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_AUTO_PROMOTE_ENABLED",
        description=(
            "If true, the server will periodically attempt deterministic loop progression. "
            "This includes Step 1a kick-off (open + assign a gap analysis issue when none exists), "
            "Step 2a promotion (pending file -> issue -> assign), Step 1c/2c/3c merges (when safe), "
            "and Step 3a legacy capability promotion for capability queue artefacts."
        ),
    )
    auto_promote_interval_seconds: float = Field(
        default=30.0,
        validation_alias="ORCHESTRATOR_AUTO_PROMOTE_INTERVAL_SECONDS",
        description="Polling interval (seconds) for auto promotion when enabled.",
    )

    auto_heal_orphaned_processed_queue_items: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_AUTO_HEAL_ORPHANED_PROCESSED_QUEUE_ITEMS",
        description=(
            "If true, the server may attempt to automatically heal orphaned development queue artefacts "
            "that are stuck under .agent-orchestrator/issue_queue/processed with no associated open issue/PR. "
            "Healing is conservative: it only marks a processed artefact complete when it can prove a linked PR "
            "was merged; in build mode it will also ensure an 'Update Capability' follow-up issue exists."
        ),
    )

    auto_resume_copilot_on_rate_limit: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT",
        description=(
            "If true, the server may automatically post a '@copilot ... resume' comment on a PR "
            "after detecting that Copilot SWE Agent has stopped (via issue lifecycle events) and "
            "waiting the configured delay."
        ),
    )
    auto_resume_copilot_on_rate_limit_delay_minutes: int = Field(
        default=45,
        validation_alias="ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT_DELAY_MINUTES",
        description=(
            "Delay (minutes) to wait after the Copilot stop/failure timestamp before posting an "
            "auto-resume comment."
        ),
        ge=1,
        le=240,
    )

    auto_link_focused_issue_pr: bool = Field(
        default=False,
        validation_alias="ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR",
        description=(
            "If true, the server may attempt to auto-link the focused issue to a likely open PR "
            "(for the current loop stage) when GitHub linkage signals are missing. This is best-effort "
            "and only runs when the loop has a focused issue but no linked PR."
        ),
    )

    auto_resume_copilot_max_nudges: int = Field(
        default=3,
        validation_alias="ORCHESTRATOR_AUTO_RESUME_COPILOT_MAX_NUDGES",
        description=(
            "Maximum number of auto-resume nudges that may be posted within the active window "
            "(see ORCHESTRATOR_AUTO_RESUME_COPILOT_NUDGE_WINDOW_MINUTES). Set to 0 to disable "
            "posting while keeping detection enabled."
        ),
        ge=0,
        le=20,
    )
    auto_resume_copilot_nudge_window_minutes: int = Field(
        default=1440,
        validation_alias="ORCHESTRATOR_AUTO_RESUME_COPILOT_NUDGE_WINDOW_MINUTES",
        description=(
            "Rolling window (minutes) used to count previously-posted resume nudges when enforcing "
            "the nudge budget."
        ),
        ge=10,
        le=10080,
    )

    # Active repository context for the dashboard. If set, issue lists and overview
    # will be scoped to this repo by default.
    default_repo: str = Field(default="", validation_alias="ORCHESTRATOR_DEFAULT_REPO")

    loop_mode: str = Field(
        default="build",
        validation_alias="ORCHESTRATOR_LOOP_MODE",
        description=(
            "Controls the orchestrator loop semantics. 'build' runs the goal/capabilities-driven "
            "gap-analysis → development → capability-update cycle. 'review' runs the "
            "review-consumption → development → review-actions-update cycle."
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

    # Where the Vite build output lives when serving the UI from the backend.
    ui_dist_path: Path = Field(default=Path("ui/dist"), validation_alias="ORCHESTRATOR_UI_DIST")

    # Dev-friendly CORS (Vite). Override via ORCHESTRATOR_CORS_ORIGINS=...
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="ORCHESTRATOR_CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins.",
    )

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    @field_validator("loop_mode")
    @classmethod
    def _validate_loop_mode(cls, v: str) -> str:
        mode = (v or "").strip().lower()
        if mode in {"build", "review"}:
            return mode
        raise ValueError("ORCHESTRATOR_LOOP_MODE must be one of: build, review")

    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
