"""Status route for repository control-plane state."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import Settings
from backend.app.github.auth import create_github_client
from backend.app.models.control_plane import RepositoryStatusResponse
from backend.app.routes.auth import require_authenticated_user
from backend.app.services.status import get_status


router = APIRouter(tags=["status"], dependencies=[Depends(require_authenticated_user)])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@router.get("/repos/{owner}/{repo}/status", response_model=RepositoryStatusResponse)
async def get_repo_status(
    owner: str,
    repo: str,
    workflow_file: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> RepositoryStatusResponse:
    selected_workflow = workflow_file or settings.default_workflow_file
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        payload = await get_status(client, owner, repo, workflow_file=selected_workflow)
        return RepositoryStatusResponse.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to read repository status: {exc}") from exc
