"""FastAPI app factory.

Endpoints are intentionally thin wrappers over the existing orchestrator services.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueRecord,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.server.job_store import JobStore
from github_agent_orchestrator.server.models import ApiIssue, JobStatus, MonitorJob, MonitorRequest
from github_agent_orchestrator.server.monitor_runner import start_monitor_job

logger = logging.getLogger(__name__)


def _iso_to_dt(value: str) -> datetime:
    # Best-effort parsing; the store always writes ISO format.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=UTC)


def _to_api_issue(record: IssueRecord) -> ApiIssue:
    return ApiIssue.model_validate(record.model_dump(mode="json"))


def create_app() -> FastAPI:
    settings = OrchestratorSettings()

    app = FastAPI(
        title="GitHub Agent Orchestrator",
        version="0.1.0",
        description="REST API over the local-first github-agent-orchestrator services.",
    )

    # Minimal dev-friendly CORS so a Vite dev server can call the API.
    # Tighten this later (e.g., ORCHESTRATOR_CORS_ORIGINS).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    issue_store = IssueStore(settings.issues_state_file)
    job_store = JobStore(settings.agent_state_path / "jobs.json")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/issues", response_model=list[ApiIssue])
    def list_issues() -> list[ApiIssue]:
        issues = issue_store.load()
        return [_to_api_issue(issue) for issue in issues]

    @app.get("/api/v1/issues/{issue_number}", response_model=ApiIssue)
    def get_issue(issue_number: int) -> ApiIssue:
        record = issue_store.find_by_number(issue_number)
        if record is None:
            raise HTTPException(status_code=404, detail="Issue not found in local state")
        return _to_api_issue(record)

    @app.post("/api/v1/issues/{issue_number}/refresh-prs", response_model=ApiIssue)
    def refresh_prs(issue_number: int) -> ApiIssue:
        github = GitHubClient(
            token=settings.github_token,
            repository=_infer_repo_from_state_or_fail(issue_number, issue_store),
            base_url=settings.github_base_url,
        )
        try:
            service = IssueService(github=github, store=issue_store)
            updated = service.refresh_linked_pull_requests(issue_number=issue_number)
            if updated is None:
                raise HTTPException(status_code=404, detail="Issue not found in local state")
            return _to_api_issue(updated)
        finally:
            github.close()

    @app.post("/api/v1/issues/{issue_number}/monitor-prs", response_model=MonitorJob)
    def monitor_prs(issue_number: int, req: MonitorRequest) -> MonitorJob:
        repository = _infer_repo_from_state_or_fail(issue_number, issue_store)
        job_id = start_monitor_job(
            repository=repository,
            issue_number=issue_number,
            poll_seconds=req.poll_seconds,
            timeout_seconds=req.timeout_seconds,
            require_pr=req.require_pr,
            settings=settings,
            job_store=job_store,
        )
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=500, detail="Job creation failed")
        return MonitorJob(
            job_id=record.job_id,
            issue_number=record.issue_number,
            status=cast(JobStatus, record.status),
            created_at=_iso_to_dt(record.created_at),
            updated_at=_iso_to_dt(record.updated_at),
            completion=record.completion,
            pull_request_numbers=record.pull_request_numbers,
            error=record.error,
        )

    @app.get("/api/v1/jobs/{job_id}", response_model=MonitorJob)
    def get_job(job_id: str) -> MonitorJob:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return MonitorJob(
            job_id=record.job_id,
            issue_number=record.issue_number,
            status=cast(JobStatus, record.status),
            created_at=_iso_to_dt(record.created_at),
            updated_at=_iso_to_dt(record.updated_at),
            completion=record.completion,
            pull_request_numbers=record.pull_request_numbers,
            error=record.error,
        )

    return app


def _infer_repo_from_state_or_fail(issue_number: int, store: IssueStore) -> str:
    """Infer the repository from local state.

    Phase 1/1A state does not currently persist repo, so for now we require the
    user to run the server for a single repo at a time.

    We'll evolve state to include repo later.
    """

    record = store.find_by_number(issue_number)
    if record is None:
        raise HTTPException(status_code=404, detail="Issue not found in local state")

    if record.repository.strip():
        return record.repository.strip()

    # Backward-compatibility fallback for pre-repo state files.
    import os

    repo = os.getenv("ORCHESTRATOR_DEFAULT_REPO", "").strip()
    if not repo:
        raise HTTPException(
            status_code=409,
            detail=(
                "Issue state does not include repository. "
                "Recreate issues with a newer orchestrator, or set ORCHESTRATOR_DEFAULT_REPO=owner/repo."
            ),
        )
    return repo
