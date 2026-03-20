"""Workflow control routes (start/stop)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.github.auth import create_github_client
from backend.app.routes.auth import require_authenticated_user
from backend.app.services.workflows import cancel_latest_run, dispatch_workflow


router = APIRouter(tags=["actions"], dependencies=[Depends(require_authenticated_user)])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


class StartLoopRequest(BaseModel):
    workflow_file: str | None = None
    ref: str = Field(default="main")


class StopLoopRequest(BaseModel):
    workflow_file: str | None = None


@router.post("/repos/{owner}/{repo}/start")
async def start_loop(
    owner: str,
    repo: str,
    payload: StartLoopRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    workflow_file = payload.workflow_file or settings.default_workflow_file
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        return await dispatch_workflow(
            client,
            owner,
            repo,
            workflow_file=workflow_file,
            ref=payload.ref,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to dispatch workflow: {exc}") from exc


@router.post("/repos/{owner}/{repo}/stop")
async def stop_loop(
    owner: str,
    repo: str,
    payload: StopLoopRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    workflow_file = payload.workflow_file or settings.default_workflow_file
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        return await cancel_latest_run(client, owner, repo, workflow_file=workflow_file)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to cancel workflow run: {exc}") from exc
