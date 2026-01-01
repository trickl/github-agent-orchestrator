"""CLI entrypoint for the local-first orchestrator.

Phase 1/1A only: configuration + structured logging + GitHub issue creation.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from github_agent_orchestrator import __version__
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.orchestrator.issue_queue_completion import plan_move_to_complete
from github_agent_orchestrator.orchestrator.logging import configure_logging
from github_agent_orchestrator.orchestrator.planning.issue_queue import (
    QUEUE_MARKER_PREFIX,
    discover_pending_items,
    move_to_processed,
    parse_issue_queue_item,
)
from github_agent_orchestrator.orchestrator.system_capabilities_after_merge import render_issue_body

logger = logging.getLogger(__name__)


def _parse_labels(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    labels = [p for p in parts if p]
    return labels or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="Local-first GitHub agent orchestrator (Phase 1/1A)",
    )
    parser.add_argument(
        "--version", action="version", version=f"github-agent-orchestrator {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_issue = subparsers.add_parser("create-issue", help="Create a GitHub issue")
    create_issue.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    create_issue.add_argument("--title", required=True, help="Issue title")
    create_issue.add_argument("--body", default=None, help="Issue body")
    create_issue.add_argument(
        "--labels",
        default=None,
        help="Comma-separated labels, e.g. 'agent,phase-1'",
    )

    assign_copilot = subparsers.add_parser(
        "assign-copilot",
        help="Assign an existing issue to Copilot (assignee login configurable via COPILOT_ASSIGNEE)",
    )
    assign_copilot.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    assign_copilot.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number to assign",
    )
    assign_copilot.add_argument(
        "--target-repo",
        default=None,
        help=(
            "Repository where Copilot will work (defaults to the same repo as the issue), "
            "in the form 'owner/repo'"
        ),
    )
    assign_copilot.add_argument(
        "--base-branch",
        default="",
        help="Base branch for Copilot work (defaults to repository default branch)",
    )
    assign_copilot.add_argument(
        "--instructions",
        default="",
        help="Optional additional instructions for Copilot",
    )
    assign_copilot.add_argument(
        "--custom-agent",
        default="",
        help="Optional custom agent identifier (public preview; may be ignored)",
    )
    assign_copilot.add_argument(
        "--model",
        default="",
        help="Optional model identifier for Copilot coding agent (public preview; may be ignored)",
    )
    assign_copilot.add_argument(
        "--reassign",
        action="store_true",
        help="Unassign Copilot (if present) then assign again to retrigger the agent",
    )

    monitor_prs = subparsers.add_parser(
        "monitor-prs",
        help="Poll for pull requests linked to an issue until they are complete",
    )
    monitor_prs.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    monitor_prs.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number to monitor",
    )
    monitor_prs.add_argument(
        "--poll-seconds",
        type=float,
        default=10.0,
        help="Polling interval in seconds",
    )
    monitor_prs.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Timeout in seconds (0 means no timeout)",
    )
    monitor_prs.add_argument(
        "--no-require-pr",
        action="store_true",
        help="Don't wait for a linked PR to appear; return immediately if none exists",
    )

    merge_linked_prs = subparsers.add_parser(
        "merge-linked-prs",
        help=(
            "Wait for linked PRs, mark them ready for review, then attempt to merge and "
            "optionally delete the merged branches"
        ),
    )
    merge_linked_prs.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    merge_linked_prs.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number whose linked PRs should be merged",
    )
    merge_linked_prs.add_argument(
        "--poll-seconds",
        type=float,
        default=10.0,
        help="Polling interval in seconds",
    )
    merge_linked_prs.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Timeout in seconds (0 means no timeout)",
    )
    merge_linked_prs.add_argument(
        "--merge-method",
        default="squash",
        help="Merge method: merge | squash | rebase",
    )
    merge_linked_prs.add_argument(
        "--no-mark-ready",
        action="store_true",
        help="Do not convert draft PRs to ready-for-review",
    )
    merge_linked_prs.add_argument(
        "--no-delete-branch",
        action="store_true",
        help="Do not delete the merged PR branch",
    )

    gap_cycle = subparsers.add_parser(
        "gap-analysis-cycle",
        help=(
            "Create a Gap Analysis issue from template, assign it to Copilot, then wait for "
            "the linked PR and merge it"
        ),
    )
    gap_cycle.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    gap_cycle.add_argument(
        "--template",
        default=str(Path("planning/issue_templates/gap-analysis.md")),
        help="Path to the gap analysis issue body template",
    )
    gap_cycle.add_argument(
        "--labels",
        default="planning,gap-analysis",
        help="Comma-separated labels to apply to the created issue",
    )
    gap_cycle.add_argument(
        "--target-repo",
        default=None,
        help=(
            "Repository where Copilot will work (defaults to the same repo as the issue), "
            "in the form 'owner/repo'"
        ),
    )
    gap_cycle.add_argument(
        "--base-branch",
        default="",
        help="Base branch for Copilot work (defaults to repository default branch)",
    )
    gap_cycle.add_argument(
        "--instructions",
        default="",
        help="Optional additional instructions for Copilot",
    )
    gap_cycle.add_argument(
        "--reassign",
        action="store_true",
        help="Unassign Copilot (if present) then assign again to retrigger the agent",
    )
    gap_cycle.add_argument(
        "--poll-seconds",
        type=float,
        default=10.0,
        help="Polling interval in seconds",
    )
    gap_cycle.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Timeout in seconds (0 means no timeout)",
    )
    gap_cycle.add_argument(
        "--merge-method",
        default="squash",
        help="Merge method: merge | squash | rebase",
    )
    gap_cycle.add_argument(
        "--no-mark-ready",
        action="store_true",
        help="Do not convert draft PRs to ready-for-review",
    )
    gap_cycle.add_argument(
        "--no-delete-branch",
        action="store_true",
        help="Do not delete the merged PR branch",
    )

    promote_queue = subparsers.add_parser(
        "promote-issue-queue",
        help=(
            "Promote the next file in planning/issue_queue/pending into a GitHub issue, "
            "assign it to Copilot, then move the file to processed/"
        ),
    )
    promote_queue.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    promote_queue.add_argument(
        "--pending-dir",
        default=str(Path("planning/issue_queue/pending")),
        help="Directory containing pending queue files",
    )
    promote_queue.add_argument(
        "--processed-dir",
        default=str(Path("planning/issue_queue/processed")),
        help="Directory where processed queue files are moved",
    )
    promote_queue.add_argument(
        "--labels",
        default="planning",
        help="Comma-separated labels to apply when creating an issue",
    )
    promote_queue.add_argument(
        "--target-repo",
        default=None,
        help=(
            "Repository where Copilot will work (defaults to the same repo as the issue), "
            "in the form 'owner/repo'"
        ),
    )
    promote_queue.add_argument(
        "--base-branch",
        default="",
        help="Base branch for Copilot work (defaults to repository default branch)",
    )
    promote_queue.add_argument(
        "--instructions",
        default="",
        help="Optional additional instructions for Copilot",
    )
    promote_queue.add_argument(
        "--reassign",
        action="store_true",
        help="Unassign Copilot (if present) then assign again to retrigger the agent",
    )

    sys_caps_after_merge = subparsers.add_parser(
        "system-capabilities-after-merge",
        help=(
            "Create a post-merge system capabilities update issue from PR metadata and discussion, "
            "assign it to Copilot"
        ),
    )
    sys_caps_after_merge.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    sys_caps_after_merge.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="Merged pull request number",
    )
    sys_caps_after_merge.add_argument(
        "--template",
        default=str(Path("planning/issue_templates/system-capabilities-after-pr-merge.md")),
        help="Path to the system capabilities after-merge issue body template",
    )
    sys_caps_after_merge.add_argument(
        "--labels",
        default="planning,system-capabilities",
        help="Comma-separated labels to apply to the created issue",
    )
    sys_caps_after_merge.add_argument(
        "--target-repo",
        default=None,
        help=(
            "Repository where Copilot will work (defaults to the same repo as the issue), "
            "in the form 'owner/repo'"
        ),
    )
    sys_caps_after_merge.add_argument(
        "--base-branch",
        default="",
        help="Base branch for Copilot work (defaults to repository default branch)",
    )
    sys_caps_after_merge.add_argument(
        "--instructions",
        default="",
        help="Optional additional instructions for Copilot",
    )
    sys_caps_after_merge.add_argument(
        "--custom-agent",
        default="",
        help="Optional custom agent identifier (public preview; may be ignored)",
    )
    sys_caps_after_merge.add_argument(
        "--model",
        default="",
        help="Optional model identifier for Copilot coding agent (public preview; may be ignored)",
    )
    sys_caps_after_merge.add_argument(
        "--reassign",
        action="store_true",
        help="Unassign Copilot (if present) then assign again to retrigger the agent",
    )
    sys_caps_after_merge.add_argument(
        "--allow-unmerged",
        action="store_true",
        help="Allow creating the issue even if the PR is not marked merged",
    )

    complete_queue_item = subparsers.add_parser(
        "complete-issue-queue-item",
        help=(
            "Create a PR that moves a pending issue-queue file to issue_queue/complete, "
            "and optionally merge it"
        ),
    )
    complete_queue_item.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    complete_queue_item.add_argument(
        "--queue-path",
        required=True,
        help=(
            "Path to the queue file in the target repo, e.g. "
            "planning/issue_queue/pending/dev-20250101.md"
        ),
    )
    complete_queue_item.add_argument(
        "--complete-dir",
        default="planning/issue_queue/complete",
        help="Destination directory for completed items",
    )
    complete_queue_item.add_argument(
        "--branch",
        default="",
        help="Optional explicit branch name for the move PR",
    )
    complete_queue_item.add_argument(
        "--merge-method",
        default="squash",
        help="Merge method: merge | squash | rebase",
    )
    complete_queue_item.add_argument(
        "--no-merge",
        action="store_true",
        help="Create the PR but do not attempt to merge it",
    )
    complete_queue_item.add_argument(
        "--no-delete-branch",
        action="store_true",
        help="Do not delete the branch after merge",
    )
    complete_queue_item.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Polling interval while waiting for mergeability",
    )
    complete_queue_item.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Timeout while attempting to merge",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = OrchestratorSettings()
    except ValidationError as e:
        # Logging isn't configured yet; keep it simple and actionable.
        print("Configuration error (check your .env):", file=sys.stderr)
        print(e, file=sys.stderr)
        return 2

    configure_logging(settings.log_level)

    try:
        if args.command == "create-issue":
            labels = _parse_labels(args.labels)

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

        if args.command == "assign-copilot":
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

        if args.command == "monitor-prs":
            github = GitHubClient(
                token=settings.github_token,
                repository=args.repository,
                base_url=settings.github_base_url,
            )
            try:
                store = IssueStore(settings.issues_state_file)
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

                # Exit codes are designed to be CI-friendly.
                if result.completion == "merged":
                    return 0
                if result.completion in {"closed", "timeout"}:
                    return 4
                if result.completion == "no_pr":
                    return 5
                return 0
            finally:
                github.close()

        if args.command == "merge-linked-prs":
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

        if args.command == "gap-analysis-cycle":
            title = "Identify the next most important development gap"
            labels = _parse_labels(args.labels)
            template_path = Path(args.template)
            body = template_path.read_text(encoding="utf-8")

            github = GitHubClient(
                token=settings.github_token,
                repository=args.repository,
                base_url=settings.github_base_url,
            )
            try:
                store = IssueStore(settings.issues_state_file)
                service = IssueService(github=github, store=store)

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
                    )
                else:
                    service.assign_issue_to_copilot(
                        issue_number=record.issue_number,
                        copilot_assignee=settings.copilot_assignee,
                        target_repo=target_repo,
                        base_branch=args.base_branch,
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
                    print(
                        f"No open linked PRs found for issue #{record.issue_number} within timeout"
                    )
                    return 5

                all_merged = all(o.merged for o in outcomes)
                for o in outcomes:
                    print(
                        f"PR #{o.pull_number}: merged={o.merged} branch_deleted={o.branch_deleted} ({o.message})"
                    )
                return 0 if all_merged else 4
            finally:
                github.close()

        if args.command == "promote-issue-queue":
            labels = _parse_labels(args.labels)

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
                    return 0

                # One issue per cycle: promote the next file and exit.
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
                    print(
                        f"Issue already exists: #{queue_record.issue_number} '{queue_record.title}'"
                    )

                assert queue_record is not None

                target_repo = args.target_repo or args.repository
                if args.reassign:
                    service.reassign_issue_to_copilot(
                        issue_number=queue_record.issue_number,
                        copilot_assignee=settings.copilot_assignee,
                        target_repo=target_repo,
                        base_branch=args.base_branch,
                        custom_instructions=args.instructions,
                    )
                else:
                    # Avoid unnecessary assignments if Copilot is already on the issue.
                    current_assignees = github.get_issue_assignees(
                        issue_number=queue_record.issue_number
                    )
                    if not any("copilot" in a.lower() for a in current_assignees):
                        service.assign_issue_to_copilot(
                            issue_number=queue_record.issue_number,
                            copilot_assignee=settings.copilot_assignee,
                            target_repo=target_repo,
                            base_branch=args.base_branch,
                            custom_instructions=args.instructions,
                        )

                moved = move_to_processed(item_path=item.path, processed_dir=processed_dir)
                print(f"Moved queue file to {moved}")
                return 0
            finally:
                github.close()

        if args.command == "system-capabilities-after-merge":
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

        if args.command == "complete-issue-queue-item":
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

                # If already completed (source missing), exit cleanly.
                try:
                    source_text, source_sha = github.get_text_file_from_repo(
                        path=plan.source_path, ref=default_branch
                    )
                except FileNotFoundError:
                    print("Queue item not found in pending; nothing to do")
                    return 0

                # If destination already exists, treat as complete and exit.
                try:
                    github.get_text_file_from_repo(path=plan.dest_path, ref=default_branch)
                    print("Queue item already present in complete; nothing to do")
                    return 0
                except FileNotFoundError:
                    pass

                branch = args.branch.strip()
                if not branch:
                    # Deterministic-ish branch name; avoids whitespace and keeps it readable.
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

                started = time.monotonic()
                while True:
                    pr_details = github.get_pull_request(pull_number=created.number)

                    if pr_details.merged:
                        print(f"PR #{created.number} already merged")
                        break

                    merge = github.merge_pull_request(
                        pull_number=created.number,
                        merge_method=args.merge_method,
                    )
                    if merge.merged:
                        print(f"Merged PR #{created.number}")
                        break

                    if (
                        args.timeout_seconds
                        and (time.monotonic() - started) >= args.timeout_seconds
                    ):
                        print(f"Timed out merging PR #{created.number}: {merge.message}")
                        return 4

                    time.sleep(args.poll_seconds)

                if not args.no_delete_branch:
                    try:
                        deleted = github.delete_pull_request_branch(pull_number=created.number)
                        if deleted:
                            print(f"Deleted branch for PR #{created.number}")
                    except Exception:
                        logger.exception(
                            "Failed to delete branch (continuing)",
                            extra={"pull_number": created.number, "repo": args.repository},
                        )

                return 0
            finally:
                github.close()

        logger.error("Unknown command", extra={"command": args.command})
        return 2

    except IssueAlreadyExists as e:
        logger.warning(
            str(e), extra={"issue_number": e.existing.issue_number, "title": e.existing.title}
        )
        print(str(e), file=sys.stderr)
        return 3

    except Exception:
        logger.exception("Command failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
