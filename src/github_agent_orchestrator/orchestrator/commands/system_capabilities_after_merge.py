"""Handler for system-capabilities-after-merge command."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.orchestrator.system_capabilities_after_merge import render_issue_body

logger = logging.getLogger(__name__)


def handle_system_capabilities_after_merge(
    args: argparse.Namespace, settings: OrchestratorSettings
) -> int:
    """Handle the system-capabilities-after-merge command."""
    from github_agent_orchestrator.orchestrator.main import _parse_labels

    labels = _parse_labels(args.labels)
    template_path = Path(args.template)
    template = template_path.read_text(encoding="utf-8")

    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        store = IssueStore(settings.issues_state_file)
        service = IssueService(github=github, store=store)

        pr = github.get_pull_request_content(pull_number=args.pr_number)
        if not pr.merged and not args.allow_unmerged:
            print(
                f"PR #{args.pr_number} is not marked merged; refusing to create issue. "
                "(Use --allow-unmerged to override.)"
            )
            return 4

        discussion = github.get_pull_request_discussion(pull_number=args.pr_number)

        title = f"Update system capabilities based on merged PR #{pr.number}"
        body = render_issue_body(template=template, pr=pr, discussion=discussion)

        try:
            record = service.create_issue(title=title, body=body, labels=labels)
        except IssueAlreadyExists as e:
            record = e.existing
            print(f"Issue already exists: #{record.issue_number} '{record.title}'")

        target_repo = args.target_repo or args.repository
        if args.reassign:
            service.reassign_issue_to_copilot(
                issue_number=record.issue_number,
                copilot_assignee=settings.copilot_assignee,
                target_repo=target_repo,
                base_branch=args.base_branch,
                custom_instructions=args.instructions,
                custom_agent=args.custom_agent,
                model=args.model,
            )
        else:
            service.assign_issue_to_copilot(
                issue_number=record.issue_number,
                copilot_assignee=settings.copilot_assignee,
                target_repo=target_repo,
                base_branch=args.base_branch,
                custom_instructions=args.instructions,
                custom_agent=args.custom_agent,
                model=args.model,
            )

        print(f"Assigned issue #{record.issue_number} to {settings.copilot_assignee}")
        return 0
    finally:
        github.close()
