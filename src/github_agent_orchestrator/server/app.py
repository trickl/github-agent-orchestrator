"""FastAPI app factory.

The server exposes the dashboard API at `/api` and (optionally) serves the built UI.

Design principle: no legacy compatibility surfaces. Old interfaces are removed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard_router import router as dashboard_router

logger = logging.getLogger(__name__)


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

    _maybe_mount_ui(app, settings)
    return app


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
