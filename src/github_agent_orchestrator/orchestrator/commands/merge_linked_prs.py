"""Handler for merge-linked-prs command."""

from __future__ import annotations

import argparse
import logging

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore

logger = logging.getLogger(__name__)


def handle_merge_linked_prs(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the merge-linked-prs command."""
    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        store = IssueStore(settings.issues_state_file)
        service = IssueService(github=github, store=store)

        outcomes = service.merge_linked_pull_requests(
            issue_number=args.issue_number,
            poll_interval_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            merge_method=args.merge_method,
            mark_ready_for_review=not args.no_mark_ready,
            delete_branch=not args.no_delete_branch,
        )

        if not outcomes:
            print(f"No open linked PRs found for issue #{args.issue_number}")
            return 5

        all_merged = all(o.merged for o in outcomes)
        for o in outcomes:
            print(
                f"PR #{o.pull_number}: merged={o.merged} branch_deleted={o.branch_deleted} ({o.message})"
            )
        return 0 if all_merged else 4
    finally:
        github.close()
