"""FastAPI application for the lightweight local control-plane backend."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from importlib import metadata

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes.actions import router as actions_router
from backend.app.routes.events import router as events_router
from backend.app.routes.repos import router as repos_router
from backend.app.routes.status import router as status_router
from backend.app.routes.webhooks import router as webhooks_router


def _resolve_backend_version() -> str:
    try:
        from github_agent_orchestrator import __version__

        return __version__
    except Exception:
        pass

    try:
        return metadata.version("github-agent-orchestrator")
    except metadata.PackageNotFoundError:
        return "0.0.0"


BACKEND_VERSION = _resolve_backend_version()


app = FastAPI(
    title="GitHub Agent Orchestrator Control Plane",
    version=BACKEND_VERSION,
    description=(
        "Local backend for PAT-authenticated GitHub operations and local orchestrator execution."
    ),
)


def _cors_origins_from_env() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "https://trickl.github.io,http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, object]:
    return {"ok": True, "service": "control-plane-backend"}


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "control-plane-backend"}


@app.get("/version")
async def version() -> dict[str, object]:
    git_sha = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")
        or "unknown"
    )
    return {
        "service": "control-plane-backend",
        "version": BACKEND_VERSION,
        "gitSha": git_sha,
        "buildTimeUtc": os.getenv("BUILD_TIME_UTC", datetime.now(UTC).isoformat()),
    }


app.include_router(repos_router)
app.include_router(actions_router)
app.include_router(status_router)
app.include_router(webhooks_router)
app.include_router(events_router)
