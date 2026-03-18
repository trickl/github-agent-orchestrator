"""Handler for monitor-prs command."""

from __future__ import annotations

import argparse
import logging

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, NullIssueStore

logger = logging.getLogger(__name__)


def handle_monitor_prs(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the monitor-prs command."""
    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        store = NullIssueStore()
        service = IssueService(github=github, store=store)

        result = service.wait_for_linked_pull_requests_complete(
            issue_number=args.issue_number,
            poll_interval_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            require_pull_request=not args.no_require_pr,
        )

        pr_numbers = [pr.number for pr in result.pull_requests]
        print(
            f"Issue #{args.issue_number} linked PRs: {pr_numbers or 'none'}; completion={result.completion}"
        )

        if result.completion == "merged":
            return 0
        if result.completion in {"closed", "timeout"}:
            return 4
        if result.completion == "no_pr":
            return 5
        return 0
    finally:
        github.close()
