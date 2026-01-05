"""Handler for auto-resume-copilot command."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def handle_auto_resume_copilot(args: argparse.Namespace, settings: Any) -> int:  # noqa: ARG001
    """Handle the auto-resume-copilot command.

    Note: This command uses ServerSettings internally, not OrchestratorSettings.
    The settings parameter is unused but kept for consistent handler signature.
    """
    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    from github_agent_orchestrator.server.config import ServerSettings

    server_settings = ServerSettings()
    if args.force_enabled:
        server_settings = server_settings.model_copy(
            update={"auto_resume_copilot_on_rate_limit": True}
        )
    if args.delay_minutes is not None:
        server_settings = server_settings.model_copy(
            update={"auto_resume_copilot_on_rate_limit_delay_minutes": args.delay_minutes}
        )

    if not server_settings.github_token.strip():
        print(
            "No GitHub token configured (set ORCHESTRATOR_GITHUB_TOKEN).",
            file=sys.stderr,
        )
        return 2

    msg = dashboard_router._maybe_auto_resume_copilot_after_rate_limit(
        settings=server_settings,
        repository=args.repository,
        pr_number=args.pr_number,
    )
    print(msg or "No auto-resume action taken.")

    try:
        comments = dashboard_router._list_issue_comments_raw(
            server_settings,
            repository=args.repository,
            issue_number=args.pr_number,
        )
    except Exception as e:
        print(f"Failed to verify issue comments: {e}", file=sys.stderr)
        return 1

    found = False
    for it in comments:
        if not isinstance(it, dict):
            continue
        comment_body = it.get("body")
        if isinstance(comment_body, str) and dashboard_router._comment_body_is_copilot_resume_nudge(
            comment_body
        ):
            found = True
            break

    if found:
        print(
            f"Confirmed: resume nudge comment is present on {args.repository} PR #{args.pr_number}."
        )
        return 0

    print(
        f"Not confirmed: resume nudge comment not present on {args.repository} PR #{args.pr_number}.",
        file=sys.stderr,
    )
    return 4
