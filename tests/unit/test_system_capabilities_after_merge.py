from __future__ import annotations

from datetime import UTC, datetime

from github_agent_orchestrator.orchestrator.github.client import (
    PullRequestContent,
    PullRequestDiscussionItem,
)
from github_agent_orchestrator.orchestrator.system_capabilities_after_merge import (
    render_issue_body,
    render_pr_discussion_markdown,
)


def test_render_pr_discussion_markdown_empty() -> None:
    assert render_pr_discussion_markdown([]) == "(no PR comments)"


def test_render_issue_body_replaces_placeholders() -> None:
    template = (
        "Title: Update system capabilities based on merged PR #{{PR_NUMBER}}\n"
        "PR title: {{PR_TITLE}}\n"
        "Desc:\n{{PR_DESCRIPTION}}\n"
        "Comments:\n{{PR_COMMENTS}}\n"
    )

    pr = PullRequestContent(
        number=123,
        title="Improve dashboard wording",
        body="This PR renames generation rules to cognitive tasks.",
        state="closed",
        merged=True,
        merged_at="2025-12-31T00:00:00Z",
        html_url="https://github.com/acme/repo/pull/123",
    )

    items = [
        PullRequestDiscussionItem(
            created_at=datetime(2025, 12, 31, 12, 0, tzinfo=UTC),
            kind="ISSUE_COMMENT",
            author="alice",
            body="LGTM",
            url="https://github.com/acme/repo/pull/123#issuecomment-1",
        )
    ]

    body = render_issue_body(template=template, pr=pr, discussion=items)

    assert "#123" in body
    assert "Improve dashboard wording" in body
    assert "renames generation rules to cognitive tasks" in body
    assert "ISSUE_COMMENT" in body
    assert "alice" in body
    assert "LGTM" in body
