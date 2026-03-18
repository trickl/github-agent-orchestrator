"""Handler for gap-analysis-cycle command."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    NullIssueStore,
)
from github_agent_orchestrator.orchestrator.branching import resolve_assignment_branch
from github_agent_orchestrator.orchestrator.utils import parse_labels

logger = logging.getLogger(__name__)


def handle_gap_analysis_cycle(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the gap-analysis-cycle command."""
    title = "Identify the next most important development gap"
    labels = parse_labels(args.labels)
    template_path = Path(args.template)
    body = template_path.read_text(encoding="utf-8")

    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        store = NullIssueStore()
        service = IssueService(github=github, store=store)

        try:
            record = service.create_issue(title=title, body=body, labels=labels)
        except IssueAlreadyExists as e:
            record = e.existing
            print(f"Issue already exists: #{record.issue_number} '{record.title}'")

        target_repo = args.target_repo or args.repository
        base_branch = resolve_assignment_branch(
            github=github,
            repository=target_repo,
            issue_number=record.issue_number,
            base_branch_override=args.base_branch,
            target_base_branch=settings.target_base_branch,
            create_work_branch=settings.create_work_branch,
            work_branch_prefix=settings.work_branch_prefix,
        )
        if args.reassign:
            service.reassign_issue_to_copilot(
                issue_number=record.issue_number,
                copilot_assignee=settings.copilot_assignee,
                target_repo=target_repo,
                base_branch=base_branch,
                custom_instructions=args.instructions,
            )
        else:
            service.assign_issue_to_copilot(
                issue_number=record.issue_number,
                copilot_assignee=settings.copilot_assignee,
                target_repo=target_repo,
                base_branch=base_branch,
                custom_instructions=args.instructions,
            )

        print(f"Assigned issue #{record.issue_number} to {settings.copilot_assignee}")

        outcomes = service.merge_linked_pull_requests(
            issue_number=record.issue_number,
            poll_interval_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            merge_method=args.merge_method,
            mark_ready_for_review=not args.no_mark_ready,
            delete_branch=not args.no_delete_branch,
        )

        if not outcomes:
            print(f"No open linked PRs found for issue #{record.issue_number} within timeout")
            return 5

        all_merged = all(o.merged for o in outcomes)
        for o in outcomes:
            print(
                f"PR #{o.pull_number}: merged={o.merged} branch_deleted={o.branch_deleted} ({o.message})"
            )
        return 0 if all_merged else 4
    finally:
        github.close()
