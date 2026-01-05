"""Handler for auto-link-issue-pr command."""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def handle_auto_link_issue_pr(args: argparse.Namespace, settings: object) -> int:  # noqa: ARG001
    """Handle the auto-link-issue-pr command."""
    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    from github_agent_orchestrator.server.config import ServerSettings

    server_settings = ServerSettings()
    if args.force_enabled:
        server_settings = server_settings.model_copy(update={"auto_link_focused_issue_pr": True})

    debug: list[str] = []

    issue_url = dashboard_router._repo_api_url(
        server_settings,
        repository=args.repository,
        path=f"issues/{args.issue_number}",
    )
    issue_data = dashboard_router._github_get_json(server_settings, url=issue_url)
    issue_title = issue_data.get("title")
    if not isinstance(issue_title, str) or not issue_title.strip():
        print(
            f"Failed to read issue title for {args.repository} #{args.issue_number}.",
            file=sys.stderr,
        )
        return 1

    raw_open_prs = dashboard_router._list_open_pull_requests_raw(
        server_settings,
        repository=args.repository,
        limit=int(args.limit_open_prs),
    )

    focus = {
        "kind": "development",
        "title": issue_title,
        "issueNumber": int(args.issue_number),
        "pullNumber": None,
    }

    msg = dashboard_router._maybe_auto_link_focused_issue_to_pr(
        settings=server_settings,
        repository=args.repository,
        focus=focus,
        raw_open_prs=raw_open_prs,
        debug=debug,
    )

    print(msg or "No auto-link action taken.")
    if debug:
        print("--- auto-link debug ---")
        for line in debug:
            print(f"- {line}")

    return 0
