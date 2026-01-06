"""Handler for complete-issue-queue-item command."""

from __future__ import annotations

import argparse
import logging
import time

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.issue_queue_completion import plan_move_to_complete

logger = logging.getLogger(__name__)


def _merge_pull_request_until_complete(
    *,
    github: GitHubClient,
    pull_number: int,
    merge_method: str,
    poll_seconds: float,
    timeout_seconds: float,
) -> int:
    """Attempt to merge a PR until merged or timed out.

    Returns an exit code (0 success, 4 timeout).
    """

    started = time.monotonic()
    while True:
        pr_details = github.get_pull_request(pull_number=pull_number)
        if pr_details.merged:
            print(f"PR #{pull_number} already merged")
            return 0

        merge = github.merge_pull_request(
            pull_number=pull_number,
            merge_method=merge_method,
        )
        if merge.merged:
            print(f"Merged PR #{pull_number}")
            return 0

        if timeout_seconds and (time.monotonic() - started) >= timeout_seconds:
            print(f"Timed out merging PR #{pull_number}: {merge.message}")
            return 4

        time.sleep(poll_seconds)


def _delete_pull_request_branch_best_effort(*, github: GitHubClient, pull_number: int) -> None:
    try:
        deleted = github.delete_pull_request_branch(pull_number=pull_number)
        if deleted:
            print(f"Deleted branch for PR #{pull_number}")
    except Exception:
        logger.exception(
            "Failed to delete branch (continuing)",
            extra={"pull_number": pull_number},
        )


def handle_complete_issue_queue_item(
    args: argparse.Namespace, settings: OrchestratorSettings
) -> int:
    """Handle the complete-issue-queue-item command."""
    github = GitHubClient(
        token=settings.github_token,
        repository=args.repository,
        base_url=settings.github_base_url,
    )
    try:
        default_branch = github.get_repository_default_branch()
        plan = plan_move_to_complete(
            source_path=args.queue_path,
            complete_dir=args.complete_dir,
        )

        try:
            source_text, source_sha = github.get_text_file_from_repo(
                path=plan.source_path, ref=default_branch
            )
        except FileNotFoundError:
            print("Queue item not found in pending; nothing to do")
            return 0

        try:
            github.get_text_file_from_repo(path=plan.dest_path, ref=default_branch)
            print("Queue item already present in complete; nothing to do")
            return 0
        except FileNotFoundError:
            pass

        branch = args.branch.strip()
        if not branch:
            safe = plan.filename.replace(" ", "-")
            branch = f"orchestrator/complete-queue/{safe}"

        base_sha = github.get_branch_head_sha(branch=default_branch)
        github.create_branch(branch=branch, base_sha=base_sha)

        commit_message = f"Move {plan.filename} to issue_queue/complete"

        github.upsert_text_file_in_repo(
            path=plan.dest_path,
            content=source_text,
            branch=branch,
            message=commit_message,
        )
        github.delete_file_in_repo(
            path=plan.source_path,
            sha=source_sha,
            branch=branch,
            message=commit_message,
        )

        pr_title = f"Move {plan.filename} to issue_queue/complete"
        pr_body = (
            "This PR was created by github-agent-orchestrator to record that the work item is complete.\n\n"
            f"Source: `{plan.source_path}`\n"
            f"Destination: `{plan.dest_path}`\n"
        )

        created = github.create_pull_request(
            title=pr_title,
            body=pr_body,
            head=branch,
            base=default_branch,
        )

        if args.no_merge:
            print(f"Created PR #{created.number} (merge skipped)")
            return 0

        merge_exit = _merge_pull_request_until_complete(
            github=github,
            pull_number=created.number,
            merge_method=args.merge_method,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        if merge_exit != 0:
            return merge_exit

        if not args.no_delete_branch:
            _delete_pull_request_branch_best_effort(github=github, pull_number=created.number)

        return 0
    finally:
        github.close()
