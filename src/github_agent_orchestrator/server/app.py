"""FastAPI app factory.

The server exposes the dashboard API at `/api` and (optionally) serves the built UI.

Design principle: no legacy compatibility surfaces. Old interfaces are removed.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _ensure_gap_analysis_issue_exists,
    _merge_next_ready_pull_request,
    _promote_next_unpromoted_capability_queue_item,
    _promote_next_unpromoted_development_queue_item,
)
from github_agent_orchestrator.server.dashboard.loop_status import _loop_status_for_repo
from github_agent_orchestrator.server.dashboard_router import (
    _ensure_review_consumption_issue_exists,
)
from github_agent_orchestrator.server.dashboard_router import router as dashboard_router

logger = logging.getLogger(__name__)


_MERGE_STAGES = {"1c", "2c", "3c"}


def _extract_stage_and_open_gap_issues(status: object) -> tuple[str | None, int | None]:
    if not isinstance(status, dict):
        return None, None

    stage = status.get("stage")
    if not isinstance(stage, str):
        stage = None

    counts = status.get("counts")
    if not isinstance(counts, dict):
        return stage, None

    open_gap_issues = counts.get("openGapAnalysisIssues")
    if not isinstance(open_gap_issues, int):
        open_gap_issues = None
    return stage, open_gap_issues


def _ensure_loop_issue_exists_for_stage_1a(
    *, settings: ServerSettings, repo: str, open_gap_issues: int | None
) -> None:
    if getattr(settings, "loop_mode", "build") == "review":
        _ensure_review_consumption_issue_exists(settings=settings, repo=repo)
        logger.info("Auto review consumption issue ensured", extra={"repo": repo})
        return

    _ensure_gap_analysis_issue_exists(settings=settings, repo=repo)
    logger.info(
        "Auto gap analysis issue ensured",
        extra={"repo": repo, "open_gap_analysis_issues": open_gap_issues},
    )


def _perform_auto_action_for_stage(
    *, settings: ServerSettings, repo: str, stage: str | None, open_gap_issues: int | None
) -> None:
    if stage == "1a":
        _ensure_loop_issue_exists_for_stage_1a(
            settings=settings, repo=repo, open_gap_issues=open_gap_issues
        )
        return
    if stage == "2a":
        _promote_next_unpromoted_development_queue_item(settings=settings, repo=repo)
        logger.info("Auto promotion succeeded", extra={"repo": repo})
        return
    if stage == "3a":
        # Legacy path: capability updates represented by queue artefacts.
        _promote_next_unpromoted_capability_queue_item(settings=settings, repo=repo)
        logger.info("Auto capability promotion succeeded", extra={"repo": repo})
        return
    if stage in _MERGE_STAGES:
        _merge_next_ready_pull_request(settings=settings, repo=repo)
        logger.info("Auto merge succeeded", extra={"repo": repo})


def _auto_promotion_runner(
    *, stop: threading.Event, interval: float, settings: ServerSettings, repo: str
) -> None:
    logger.info(
        "Auto loop progression started",
        extra={"repo": repo, "interval_seconds": interval},
    )

    while not stop.is_set():
        try:
            status = _loop_status_for_repo(settings=settings, active_repo=repo, ref="")
            stage, open_gap_issues = _extract_stage_and_open_gap_issues(status)
            _perform_auto_action_for_stage(
                settings=settings,
                repo=repo,
                stage=stage,
                open_gap_issues=open_gap_issues,
            )
        except Exception as e:
            # 409 means "nothing to do"; treat as idle rather than an error.
            if getattr(e, "status_code", None) == 409:
                logger.debug(
                    "Auto progression idle",
                    extra={"repo": repo, "status_code": getattr(e, "status_code", None)},
                )
            else:
                logger.exception("Auto progression attempt failed", extra={"repo": repo})

        stop.wait(interval)

    logger.info("Auto loop progression stopped", extra={"repo": repo})


def create_app() -> FastAPI:
    settings = ServerSettings()

    app = FastAPI(
        title="GitHub Agent Orchestrator",
        version="0.1.0",
        description="REST API over the local-first github-agent-orchestrator services.",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Expose settings for request handlers that want to read it.
    app.state.settings = settings

    # Minimal dev-friendly CORS so a Vite dev server can call the API.
    # Tighten this later (e.g., ORCHESTRATOR_CORS_ORIGINS).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dashboard UI API (mounted at /api)
    app.include_router(dashboard_router, prefix="/api")

    _maybe_start_auto_promotion(app, settings)

    _maybe_mount_ui(app, settings)
    return app


def _maybe_start_auto_promotion(app: FastAPI, settings: ServerSettings) -> None:
    # Unit tests create many apps; starting a background thread can lead to non-deterministic
    # behavior and accidental network calls (e.g. from developer-local .env configuration).
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if not settings.auto_promote_enabled:
        return
    if not settings.github_token.strip():
        logger.warning(
            "Auto promotion enabled but no GitHub token configured; skipping",
            extra={"setting": "ORCHESTRATOR_AUTO_PROMOTE_ENABLED"},
        )
        return
    if not settings.default_repo.strip():
        logger.warning(
            "Auto promotion enabled but no default repo configured; skipping",
            extra={"setting": "ORCHESTRATOR_DEFAULT_REPO"},
        )
        return

    stop = threading.Event()
    app.state._auto_promote_stop = stop

    interval = max(5.0, float(settings.auto_promote_interval_seconds))
    repo = settings.default_repo.strip()

    t = threading.Thread(
        target=_auto_promotion_runner,
        kwargs={"stop": stop, "interval": interval, "settings": settings, "repo": repo},
        name="auto-promote-queue",
        daemon=True,
    )
    t.start()

    @app.on_event("shutdown")
    def _stop_auto_promote() -> None:
        stop.set()


def _maybe_mount_ui(app: FastAPI, settings: ServerSettings) -> None:
    """Serve the built dashboard UI (Vite) from the same process.

    - API is under `/api/*`
    - UI is served at `/` (SPA fallback)

    This is optional: if the UI isn't built (no `ui/dist/index.html`), we serve a small
    instruction page at `/` instead.
    """

    dist = Path(settings.ui_dist_path)
    index = dist / "index.html"

    if dist.exists() and (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="ui-assets")

    @app.get("/", include_in_schema=False, response_model=None)
    def ui_index() -> FileResponse | PlainTextResponse:
        if index.exists():
            return FileResponse(index)
        return PlainTextResponse(
            "UI not built. Run 'npm run build' in ./ui, then start the server again.\n",
            status_code=200,
        )

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def ui_spa_fallback(full_path: str) -> FileResponse:
        # Don't steal API routes.
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")

        # Serve actual files (favicon, manifest, etc.) when present.
        candidate = dist / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)

        # SPA fallback.
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="UI not built")
        # fmt: off
