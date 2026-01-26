"""Handler for promote-issue-queue command."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore
from github_agent_orchestrator.orchestrator.branching import resolve_assignment_branch
from github_agent_orchestrator.orchestrator.planning.issue_queue import (
    QUEUE_MARKER_PREFIX,
    discover_pending_items,
    move_to_processed,
    parse_issue_queue_item,
)
from github_agent_orchestrator.orchestrator.utils import parse_labels

logger = logging.getLogger(__name__)


def handle_promote_issue_queue(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the promote-issue-queue command."""
    labels = parse_labels(args.labels)

    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        store = IssueStore(settings.issues_state_file)
        service = IssueService(github=github, store=store)

        pending_dir = Path(args.pending_dir)
        processed_dir = Path(args.processed_dir)
        pending_files = discover_pending_items(pending_dir)
        if not pending_files:
            print(f"No pending queue files found in {pending_dir}")
            return 10

        item = parse_issue_queue_item(pending_files[0])
        queue_path = str(item.path.as_posix())

        queue_record = store.find_by_queue_id(item.queue_id, repository=args.repository)
        if queue_record is None:
            marker = f"{QUEUE_MARKER_PREFIX} {item.queue_id}"
            existing_number = github.find_issue_number_by_body_marker(marker=marker)
            if existing_number is not None:
                existing = github.get_issue(issue_number=existing_number)
                queue_record = service.record_existing_issue_from_queue(
                    issue=existing,
                    queue_id=item.queue_id,
                    queue_path=queue_path,
                )
            else:
                queue_record = service.create_issue_from_queue(
                    queue_id=item.queue_id,
                    queue_path=queue_path,
                    title=item.title,
                    body=item.body,
                    labels=labels,
                )
                print(f"Created issue #{queue_record.issue_number}: {queue_record.title}")
        else:
            print(f"Issue already exists: #{queue_record.issue_number} '{queue_record.title}'")

        if queue_record is None:
            raise RuntimeError("Expected an issue record to be created or discovered")

        target_repo = args.target_repo or args.repository
        base_branch = resolve_assignment_branch(
            github=github,
            repository=target_repo,
            issue_number=queue_record.issue_number,
            base_branch_override=args.base_branch,
            target_base_branch=settings.target_base_branch,
            create_work_branch=settings.create_work_branch,
            work_branch_prefix=settings.work_branch_prefix,
        )
        if args.reassign:
            service.reassign_issue_to_copilot(
                issue_number=queue_record.issue_number,
                copilot_assignee=settings.copilot_assignee,
                target_repo=target_repo,
                base_branch=base_branch,
                custom_instructions=args.instructions,
            )
        else:
            current_assignees = github.get_issue_assignees(issue_number=queue_record.issue_number)
            if not any("copilot" in a.lower() for a in current_assignees):
                service.assign_issue_to_copilot(
                    issue_number=queue_record.issue_number,
                    copilot_assignee=settings.copilot_assignee,
                    target_repo=target_repo,
                    base_branch=base_branch,
                    custom_instructions=args.instructions,
                )

        moved = move_to_processed(item_path=item.path, processed_dir=processed_dir)
        print(f"Moved queue file to {moved}")
        return 0
    finally:
        github.close()
