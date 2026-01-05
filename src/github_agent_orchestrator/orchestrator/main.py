"""CLI entrypoint for the local-first orchestrator.

Phase 1/1A only: configuration + structured logging + GitHub issue creation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from github_agent_orchestrator import __version__
from github_agent_orchestrator.orchestrator.commands import COMMAND_REGISTRY
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.issue_service import IssueAlreadyExists
from github_agent_orchestrator.orchestrator.logging import configure_logging
from github_agent_orchestrator.orchestrator.utils import parse_labels

logger = logging.getLogger(__name__)


def _parse_labels(value: str | None) -> list[str] | None:
    """Parse comma-separated labels string.

    Deprecated: Use orchestrator.utils.parse_labels instead.
    This function is kept for backward compatibility.
    """
    return parse_labels(value)


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
        default="Gap Analysis",
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
        default="Development",
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
        default="Update Capability",
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

    auto_resume_copilot = subparsers.add_parser(
        "auto-resume-copilot",
        help=(
            "Detect a Copilot SWE Agent stop/failure on a PR and (if due) post a resume nudge. "
            "This uses the same logic as the server loop status automation."
        ),
    )
    auto_resume_copilot.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    auto_resume_copilot.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="Pull request number to inspect",
    )
    auto_resume_copilot.add_argument(
        "--delay-minutes",
        type=int,
        default=None,
        help=(
            "Optional override for ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT_DELAY_MINUTES "
            "(default 45)"
        ),
    )
    auto_resume_copilot.add_argument(
        "--force-enabled",
        action="store_true",
        help=(
            "Force auto-resume enabled for this run, even if ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT "
            "is not set."
        ),
    )

    auto_link_issue_pr = subparsers.add_parser(
        "auto-link-issue-pr",
        help=(
            "Best-effort: link an issue to a likely open PR by appending 'Fixes #<issue>' to the PR body. "
            "This reuses the same logic as the server loop status automation and prints debug reasons."
        ),
    )
    auto_link_issue_pr.add_argument(
        "--repo",
        "--repository",
        dest="repository",
        required=True,
        help="Target repository in the form 'owner/repo'",
    )
    auto_link_issue_pr.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number to link",
    )
    auto_link_issue_pr.add_argument(
        "--force-enabled",
        action="store_true",
        help=(
            "Force auto-link enabled for this run, even if ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR is not set."
        ),
    )
    auto_link_issue_pr.add_argument(
        "--limit-open-prs",
        type=int,
        default=100,
        help="Maximum number of open PRs to consider (default 100)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Parses arguments, loads configuration, and dispatches to the appropriate command handler.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = OrchestratorSettings()
    except ValidationError as e:
        print("Configuration error (check your .env):", file=sys.stderr)
        print(e, file=sys.stderr)
        return 2

    configure_logging(settings.log_level)

    try:
        handler = COMMAND_REGISTRY.get(args.command)
        if handler is None:
            logger.error("Unknown command", extra={"command": args.command})
            return 2

        return handler(args, settings)

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
