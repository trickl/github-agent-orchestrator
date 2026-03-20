"""Repository-oriented control-plane routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.github.auth import create_github_client
from backend.app.models.control_plane import DispatchWorkflowResponse, UpdateOrchestratorResponse
from backend.app.routes.auth import require_authenticated_user
from backend.app.routes.dependencies import get_settings
from backend.app.services.install import initialize_repo
from backend.app.services.orchestrator_version import update_orchestrator_version
from backend.app.services.run_state import set_repo_run_state
from backend.app.services.status import list_accessible_repositories, list_development_pull_requests
from backend.app.services.target_state import upsert_target_state
from backend.app.services.workflows import dispatch_workflow


logger = logging.getLogger(__name__)


router = APIRouter(tags=["repos"], dependencies=[Depends(require_authenticated_user)])


class InitializeRepoRequest(BaseModel):
    target_state: str = Field(default="# Target State\n\nDescribe the intended end state.\n")
    orchestrator_config: str = Field(default="mode: semi\n")
    branch_name: str | None = Field(default=None)
    open_pr: bool = Field(default=True)
    apply_directly: bool = Field(default=False)


class UpsertTargetStateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    branch: str | None = Field(default=None)


class UpdateOrchestratorRequest(BaseModel):
    base_branch: str | None = Field(default=None)


class DispatchWorkflowRequest(BaseModel):
    workflow_file: str | None = Field(default=None)
    ref: str = Field(default="main")


def _diagnose_github_app_failure(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()

    if "unable to generate jwt" in lower or "could not parse the provided public key" in lower:
        return (
            "GitHub App key is invalid. Verify GITHUB_APP_ID matches the key and "
            "GITHUB_APP_PRIVATE_KEY is a full PEM private key (BEGIN/END lines, correct newlines)."
        )

    if "no github app installations available" in lower:
        return (
            "No installations found for this GitHub App. Install the app to the target account/repository "
            "and ensure installation permissions are granted."
        )

    if "installation not found" in lower:
        return (
            "GitHub App is not installed for this repository. Install the app on the repository owner "
            "and retry."
        )

    return message


@router.get("/repos")
async def list_repositories(
    settings: Settings = Depends(get_settings),
) -> list[str]:
    try:
        client = await create_github_client(settings)
        return await list_accessible_repositories(client)
    except Exception as exc:
        if "no github app installations available" in str(exc).lower():
            logger.warning("No GitHub App installations available yet; returning empty repository list")
            return []
        diagnosed = _diagnose_github_app_failure(exc)
        logger.exception("Failed to list repositories: %s", diagnosed)
        raise HTTPException(status_code=502, detail=f"Failed to list repositories: {diagnosed}") from exc


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
        diagnosed = _diagnose_github_app_failure(exc)
        logger.exception("Failed to list development PRs for %s/%s: %s", owner, repo, diagnosed)
        raise HTTPException(status_code=502, detail=f"Failed to list development PRs: {diagnosed}") from exc


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
            apply_directly=payload.apply_directly,
        )
    except Exception as exc:
        diagnosed = _diagnose_github_app_failure(exc)
        logger.exception("Failed to initialize repository %s/%s: %s", owner, repo, diagnosed)
        raise HTTPException(status_code=502, detail=f"Failed to initialize repository: {diagnosed}") from exc


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
        diagnosed = _diagnose_github_app_failure(exc)
        logger.exception("Failed to upsert target state for %s/%s: %s", owner, repo, diagnosed)
        raise HTTPException(status_code=502, detail=f"Failed to upsert target state: {diagnosed}") from exc


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
        diagnosed = _diagnose_github_app_failure(exc)
        logger.exception("Failed to update orchestrator version for %s/%s: %s", owner, repo, diagnosed)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update orchestrator version: {diagnosed}",
        ) from exc


@router.post(
    "/repos/{owner}/{repo}/run",
    response_model=DispatchWorkflowResponse,
)
async def dispatch_repo_workflow(
    owner: str,
    repo: str,
    payload: DispatchWorkflowRequest,
    settings: Settings = Depends(get_settings),
) -> DispatchWorkflowResponse:
    repo_full_name = f"{owner}/{repo}"
    workflow_file = payload.workflow_file or settings.default_workflow_file
    try:
        set_repo_run_state(repo_full_name, status="running", current_step="Dispatching workflow")
        client = await create_github_client(settings, owner=owner, repo=repo)
        dispatch_result = await dispatch_workflow(
            client,
            owner,
            repo,
            workflow_file=workflow_file,
            ref=payload.ref,
        )
        set_repo_run_state(repo_full_name, status="running", current_step="Workflow dispatched")
        return DispatchWorkflowResponse.model_validate(
            {
                "status": "dispatched",
                "repo": repo_full_name,
                "dispatched": bool(dispatch_result.get("dispatched", False)),
                "workflow": str(dispatch_result.get("workflow", workflow_file)),
                "ref": str(dispatch_result.get("ref", payload.ref)),
            }
        )
    except Exception as exc:
        logger.exception("Failed to run orchestrator for %s: %s", repo_full_name, exc)
        set_repo_run_state(repo_full_name, status="error", current_step="Workflow dispatch failed")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to run orchestrator: {exc}",
        ) from exc
