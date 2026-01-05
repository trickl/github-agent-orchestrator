"""Handler for assign-copilot command."""

from __future__ import annotations

import argparse
import logging

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore

logger = logging.getLogger(__name__)


def handle_assign_copilot(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the assign-copilot command."""
    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    store = IssueStore(settings.issues_state_file)
    service = IssueService(github=github, store=store)

    target_repo = args.target_repo or args.repository
    if args.reassign:
        updated = service.reassign_issue_to_copilot(
            issue_number=args.issue_number,
            copilot_assignee=settings.copilot_assignee,
            target_repo=target_repo,
            base_branch=args.base_branch,
            custom_instructions=args.instructions,
            custom_agent=args.custom_agent,
            model=args.model,
        )
    else:
        updated = service.assign_issue_to_copilot(
            issue_number=args.issue_number,
            copilot_assignee=settings.copilot_assignee,
            target_repo=target_repo,
            base_branch=args.base_branch,
            custom_instructions=args.instructions,
            custom_agent=args.custom_agent,
            model=args.model,
        )

    if updated is None:
        print(
            f"Assigned issue #{args.issue_number} to {settings.copilot_assignee} (not in local store)"
        )
    else:
        print(
            f"Assigned issue #{args.issue_number} to {settings.copilot_assignee} and updated local state"
        )
    return 0
