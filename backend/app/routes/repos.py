"""Repository-oriented control-plane routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.github.auth import create_github_client
from backend.app.models.control_plane import RunOrchestratorResponse, UpdateOrchestratorResponse
from backend.app.routes.auth import require_authenticated_user
from backend.app.services.install import initialize_repo
from backend.app.services.local_runner import run_orchestrator
from backend.app.services.orchestrator_version import update_orchestrator_version
from backend.app.services.run_state import set_repo_run_state
from backend.app.services.status import list_accessible_repositories, list_development_pull_requests
from backend.app.services.target_state import upsert_target_state


router = APIRouter(tags=["repos"], dependencies=[Depends(require_authenticated_user)])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


class InitializeRepoRequest(BaseModel):
    target_state: str = Field(default="# Target State\n\nDescribe the intended end state.\n")
    orchestrator_config: str = Field(default="mode: semi\n")
    branch_name: str | None = Field(default=None)
    open_pr: bool = Field(default=True)


class UpsertTargetStateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    branch: str = Field(default="main", min_length=1)


class UpdateOrchestratorRequest(BaseModel):
    base_branch: str | None = Field(default=None)


class RunOrchestratorRequest(BaseModel):
    timeout_seconds: int | None = Field(default=None, ge=1, le=10800)


@router.get("/repos")
async def list_repositories(
    settings: Settings = Depends(get_settings),
) -> list[str]:
    try:
        client = await create_github_client(settings)
        return await list_accessible_repositories(client)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list repositories: {exc}") from exc


@router.get("/repos/{owner}/{repo}/development-prs")
async def list_development_prs(
    owner: str,
    repo: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, str]]:
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        return await list_development_pull_requests(client, owner, repo)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list development PRs: {exc}") from exc


@router.post("/repos/{owner}/{repo}/initialize")
async def initialize_repository(
    owner: str,
    repo: str,
    payload: InitializeRepoRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        return await initialize_repo(
            client,
            owner,
            repo,
            target_state=payload.target_state,
            orchestrator_config=payload.orchestrator_config,
            branch_name=payload.branch_name,
            open_pr=payload.open_pr,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to initialize repository: {exc}") from exc


@router.post("/repos/{owner}/{repo}/target-state")
async def create_or_update_target_state(
    owner: str,
    repo: str,
    payload: UpsertTargetStateRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        return await upsert_target_state(
            client,
            owner,
            repo,
            payload.content,
            branch=payload.branch,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to upsert target state: {exc}") from exc


@router.post(
    "/repos/{owner}/{repo}/update-orchestrator",
    response_model=UpdateOrchestratorResponse,
)
async def update_orchestrator_runtime(
    owner: str,
    repo: str,
    payload: UpdateOrchestratorRequest,
    settings: Settings = Depends(get_settings),
) -> UpdateOrchestratorResponse:
    try:
        client = await create_github_client(settings, owner=owner, repo=repo)
        result = await update_orchestrator_version(client, owner, repo)
        return UpdateOrchestratorResponse.model_validate(result)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update orchestrator version: {exc}",
        ) from exc


@router.post(
    "/repos/{owner}/{repo}/run",
    response_model=RunOrchestratorResponse,
)
async def run_repo_orchestrator(
    owner: str,
    repo: str,
    payload: RunOrchestratorRequest,
    settings: Settings = Depends(get_settings),
) -> RunOrchestratorResponse:
    repo_full_name = f"{owner}/{repo}"
    try:
        timeout_seconds = payload.timeout_seconds or settings.orchestrator_run_timeout_seconds
        set_repo_run_state(repo_full_name, status="running", current_step="Running orchestrator")
        result = run_orchestrator(
            cli_command=settings.orchestrator_cli,
            owner=owner,
            repo=repo,
            timeout_seconds=timeout_seconds,
        )
        final_status = "idle" if result.get("exit_code") == 0 else "error"
        final_step = None if final_status == "idle" else "Orchestrator run failed"
        set_repo_run_state(repo_full_name, status=final_status, current_step=final_step)
        return RunOrchestratorResponse.model_validate(result)
    except Exception as exc:
        set_repo_run_state(repo_full_name, status="error", current_step="Orchestrator run failed")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to run orchestrator: {exc}",
        ) from exc
