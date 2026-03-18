"""FastAPI application for the lightweight local control-plane backend."""

from __future__ import annotations

from fastapi import FastAPI

from backend.app.routes.actions import router as actions_router
from backend.app.routes.events import router as events_router
from backend.app.routes.repos import router as repos_router
from backend.app.routes.status import router as status_router
from backend.app.routes.webhooks import router as webhooks_router


app = FastAPI(
    title="GitHub Agent Orchestrator Control Plane",
    version="0.1.0",
    description=(
        "Local backend for PAT-authenticated GitHub operations and local orchestrator execution."
    ),
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "control-plane-backend"}


app.include_router(repos_router)
app.include_router(actions_router)
app.include_router(status_router)
app.include_router(webhooks_router)
app.include_router(events_router)
