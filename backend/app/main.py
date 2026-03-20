"""FastAPI application for the lightweight local control-plane backend."""

from __future__ import annotations

import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes.actions import router as actions_router
from backend.app.routes.auth import router as auth_router
from backend.app.routes.events import router as events_router
from backend.app.routes.repos import router as repos_router
from backend.app.routes.status import router as status_router
from backend.app.routes.webhooks import router as webhooks_router


def _version_from_pyproject() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        raise RuntimeError("pyproject.toml not found; cannot determine backend version")
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("Unable to parse pyproject.toml for backend version") from exc

    project = data.get("project", {})
    version = project.get("version") if isinstance(project, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    raise RuntimeError("[project].version missing in pyproject.toml")


BACKEND_VERSION = _version_from_pyproject()


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
        "versionSource": "pyproject-toml",
        "gitSha": git_sha,
        "buildTimeUtc": os.getenv("BUILD_TIME_UTC", datetime.now(UTC).isoformat()),
    }


app.include_router(repos_router)
app.include_router(actions_router)
app.include_router(status_router)
app.include_router(webhooks_router)
app.include_router(events_router)
app.include_router(auth_router)
