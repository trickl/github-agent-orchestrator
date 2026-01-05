"""Handler for create-issue command."""

from __future__ import annotations

import argparse
import logging

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore
from github_agent_orchestrator.orchestrator.utils import parse_labels

logger = logging.getLogger(__name__)


def handle_create_issue(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the create-issue command."""
    labels = parse_labels(args.labels)

    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    store = IssueStore(settings.issues_state_file)
    service = IssueService(github=github, store=store)

    record = service.create_issue(title=args.title, body=args.body, labels=labels)
    logger.info(
        "Issue persisted",
        extra={
            "path": str(settings.issues_state_file),
            "issue_number": record.issue_number,
        },
    )
    print(f"Created issue #{record.issue_number}: {record.title}")
    return 0
