"""Auto-mark-ready automation for draft PRs that are blocking the merge stage.

When Copilot creates a draft PR but has signalled completion (review_requested),
the loop can stall at stage 2b/3b because draft PRs are not detected as "ready for
review" during status computation.  This module detects that situation and uses the
GitHub GraphQL ``markPullRequestReadyForReview`` mutation to unblock the loop.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_graphql_post,
    _graphql_errors_as_message,
)


def _focus_pull_number(focus: dict[str, object]) -> int | None:
    num = focus.get("pullNumber")
    return num if isinstance(num, int) and num > 0 else None


def maybe_auto_mark_focused_pr_ready(
    *,
    settings: ServerSettings,
    repository: str,
    focus: dict[str, object],
    pr_cache: dict[int, dict[str, Any]],
) -> str | None:
    """Best-effort: mark the focused PR as ready-for-review when it is still a draft.

    Safety properties:
      - opt-in via settings.auto_mark_draft_pr_ready
      - only runs when focus has a pullNumber
      - only acts when the cached PR data shows draft=True
      - idempotent: GraphQL mutation is a no-op on non-draft PRs
    """

    if not getattr(settings, "auto_mark_draft_pr_ready", True):
        return None
    if not settings.github_token.strip():
        return None

    pr_number = _focus_pull_number(focus)
    if pr_number is None:
        return None

    pr_data = pr_cache.get(pr_number)
    if not isinstance(pr_data, dict):
        return None

    if pr_data.get("draft") is not True:
        return None

    pr_node_id = pr_data.get("node_id")
    if not isinstance(pr_node_id, str) or not pr_node_id.strip():
        return None

    mutation = """
        mutation MarkReady($pullRequestId: ID!) {
            markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
                pullRequest { isDraft }
            }
        }
    """

    with suppress(HTTPException):
        payload = _github_graphql_post(
            settings,
            query=mutation,
            variables={"pullRequestId": pr_node_id},
        )
        errors = _graphql_errors_as_message(payload)
        if errors:
            return f"Auto-mark-ready failed for PR #{pr_number}: {errors}"

        # Update the cache so downstream stage computation sees the change immediately.
        pr_data["draft"] = False
        return (
            f"Auto-marked PR #{pr_number} as ready for review "
            "(was draft; Copilot signalled completion)."
        )

    return None
