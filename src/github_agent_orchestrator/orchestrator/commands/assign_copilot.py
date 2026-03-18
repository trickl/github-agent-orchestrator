"""Handler for assign-copilot command."""

from __future__ import annotations

import argparse
import logging

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.branching import resolve_assignment_branch
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, NullIssueStore

logger = logging.getLogger(__name__)


def handle_assign_copilot(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the assign-copilot command."""
    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    store = NullIssueStore()
    service = IssueService(github=github, store=store)

    target_repo = args.target_repo or args.repository
    base_branch = resolve_assignment_branch(
        github=github,
        repository=target_repo,
        issue_number=args.issue_number,
        base_branch_override=args.base_branch,
        target_base_branch=settings.target_base_branch,
        create_work_branch=settings.create_work_branch,
        work_branch_prefix=settings.work_branch_prefix,
    )
    if args.reassign:
        updated = service.reassign_issue_to_copilot(
            issue_number=args.issue_number,
            copilot_assignee=settings.copilot_assignee,
            target_repo=target_repo,
            base_branch=base_branch,
            custom_instructions=args.instructions,
            custom_agent=args.custom_agent,
            model=args.model,
        )
    else:
        updated = service.assign_issue_to_copilot(
            issue_number=args.issue_number,
            copilot_assignee=settings.copilot_assignee,
            target_repo=target_repo,
            base_branch=base_branch,
            custom_instructions=args.instructions,
            custom_agent=args.custom_agent,
            model=args.model,
        )

    if updated is None:
        print(f"Assigned issue #{args.issue_number} to {settings.copilot_assignee}")
    else:
        print(f"Assigned issue #{args.issue_number} to {settings.copilot_assignee}")
    return 0
