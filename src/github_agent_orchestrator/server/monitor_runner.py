"""Background polling runner for PR monitoring jobs."""

from __future__ import annotations

import logging
import threading
import uuid

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore
from github_agent_orchestrator.server.job_store import JobStore

logger = logging.getLogger(__name__)


def start_monitor_job(
    *,
    repository: str,
    issue_number: int,
    poll_seconds: float,
    timeout_seconds: float,
    require_pr: bool,
    settings: OrchestratorSettings,
    job_store: JobStore,
) -> str:
    job_id = uuid.uuid4().hex
    job_store.create(job_id=job_id, issue_number=issue_number)

    thread = threading.Thread(
        target=_run_job,
        name=f"monitor-prs-{issue_number}-{job_id}",
        daemon=True,
        kwargs={
            "job_id": job_id,
            "repository": repository,
            "issue_number": issue_number,
            "poll_seconds": poll_seconds,
            "timeout_seconds": timeout_seconds,
            "require_pr": require_pr,
            "settings": settings,
            "job_store": job_store,
        },
    )
    thread.start()
    return job_id


def _run_job(
    *,
    job_id: str,
    repository: str,
    issue_number: int,
    poll_seconds: float,
    timeout_seconds: float,
    require_pr: bool,
    settings: OrchestratorSettings,
    job_store: JobStore,
) -> None:
    job_store.update(job_id, status="running")

    github = GitHubClient(
        token=settings.github_token,
        repository=repository,
        base_url=settings.github_base_url,
    )
    try:
        store = IssueStore(settings.issues_state_file)
        service = IssueService(github=github, store=store)

        result = service.wait_for_linked_pull_requests_complete(
            issue_number=issue_number,
            poll_interval_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
            require_pull_request=require_pr,
        )

        status = "succeeded" if result.completion == "merged" else "failed"
        job_store.update(
            job_id,
            status=status,
            completion=result.completion,
            pull_request_numbers=[pr.number for pr in result.pull_requests],
        )

    except Exception as e:
        logger.exception(
            "Monitor job failed", extra={"job_id": job_id, "issue_number": issue_number}
        )
        job_store.update(job_id, status="failed", error=str(e))
    finally:
        github.close()
