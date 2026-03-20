"""Typed response models for control-plane repository endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OrchestratorVersionInfo(BaseModel):
    """Version metadata for orchestrator runtime in workflow files."""

    current: str | None = None
    latest: str
    updateAvailable: bool


class WorkflowMetadata(BaseModel):
    """Workflow metadata exposed by repository status APIs."""

    name: str
    orchestratorVersion: OrchestratorVersionInfo


class PullRequestSummary(BaseModel):
    """Minimal pull request summary for update workflows."""

    number: int | None = None
    url: str | None = None
    state: str | None = None


class UpdateOrchestratorResponse(BaseModel):
    """Response payload for orchestrator runtime update action."""

    owner: str
    repo: str
    branch: str
    baseBranch: str | None = None
    workflowPath: str
    current: str | None = None
    latest: str
    updateAvailable: bool
    updated: bool
    message: str | None = None
    pullRequest: PullRequestSummary | None = None


class RunOrchestratorResponse(BaseModel):
    """Response payload for orchestrator run dispatch endpoint."""

    status: str
    repo: str
    dispatched: bool
    workflow: str
    ref: str


class RepositoryStatusResponse(BaseModel):
    """Repository status payload returned to frontend clients."""

    owner: str | None = None
    repo: str | None = None
    hasTargetState: bool = False
    status: str = "idle"
    currentStep: str | None = None
    workflow_file: str | None = None
    workflow: WorkflowMetadata | None = None
    latest_run: dict[str, Any] | None = None
    status_artifact: dict[str, Any] | None = None
    active_issue_ids: list[int] = Field(default_factory=list)
    active_pr_ids: list[int] = Field(default_factory=list)
    status_artifact_validation_error: str | None = None
    workflow_orchestrator_version_error: str | None = None
