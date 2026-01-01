"""Create post-merge system-capabilities update issues.

This module renders a GitHub issue body that captures a merged PR's intent and discussion,
so Copilot can update `/planning/state/system_capabilities.md` without speculating.

The canonical body template lives in:
- planning/issue_templates/system-capabilities-after-pr-merge.md
"""

from __future__ import annotations

from collections.abc import Sequence

from github_agent_orchestrator.orchestrator.github.client import (
    PullRequestContent,
    PullRequestDiscussionItem,
)


def render_pr_discussion_markdown(items: Sequence[PullRequestDiscussionItem]) -> str:
    """Render PR discussion items as compact Markdown in chronological order."""

    if not items:
        return "(no PR comments)"

    parts: list[str] = []
    for item in items:
        ts = item.created_at.isoformat()
        header = f"- **{ts}** *( {item.kind} by {item.author} )*"
        body = (item.body or "").strip()
        if not body:
            body = "(empty)"

        # Indent to keep Markdown list formatting stable.
        indented = "\n".join(f"  {line}" for line in body.splitlines())
        parts.append("\n".join([header, indented]))

        if item.url:
            parts.append(f"  URL: {item.url}")

    return "\n".join(parts).rstrip() + "\n"


def render_issue_body(
    *,
    template: str,
    pr: PullRequestContent,
    discussion: Sequence[PullRequestDiscussionItem],
) -> str:
    """Fill the post-merge system capabilities template with PR metadata."""

    pr_description = (pr.body or "").strip() or "(no PR description)"
    pr_comments = render_pr_discussion_markdown(discussion).rstrip() or "(no PR comments)"

    # Simple placeholder replacement is intentional: templates are authored as plain Markdown.
    return (
        template.replace("{{PR_NUMBER}}", str(pr.number))
        .replace("{{PR_TITLE}}", pr.title or "")
        .replace("{{PR_DESCRIPTION}}", pr_description)
        .replace("{{PR_COMMENTS}}", pr_comments)
    )
