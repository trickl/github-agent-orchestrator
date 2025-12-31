"""Unit tests for planning issue-queue promotion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from github_agent_orchestrator.orchestrator.github.client import CreatedIssue, GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.orchestrator.planning.issue_queue import (
    QUEUE_MARKER_PREFIX,
    discover_pending_items,
    move_to_processed,
    parse_issue_queue_item,
)


def test_parse_issue_queue_item_uses_first_line_as_title_and_appends_marker(tmp_path: Path) -> None:
    pending = tmp_path / "planning" / "issue_queue" / "pending"
    pending.mkdir(parents=True)

    path = pending / "dev-2025-01-01.md"
    path.write_text("# My task title\n\nDo the thing.\n", encoding="utf-8")

    item = parse_issue_queue_item(path)

    assert item.queue_id == "dev-2025-01-01.md"
    assert item.title == "My task title"
    assert "Do the thing." in item.body
    assert f"<!-- {QUEUE_MARKER_PREFIX} {item.queue_id} -->" in item.body


def test_discover_pending_items_is_stable_sorted(tmp_path: Path) -> None:
    pending = tmp_path / "pending"
    pending.mkdir()
    (pending / "b.md").write_text("B\n", encoding="utf-8")
    (pending / "a.md").write_text("A\n", encoding="utf-8")

    items = discover_pending_items(pending)
    assert [p.name for p in items] == ["a.md", "b.md"]


def test_move_to_processed_moves_file(tmp_path: Path) -> None:
    pending = tmp_path / "pending"
    processed = tmp_path / "processed"
    pending.mkdir()

    item = pending / "dev-1.md"
    item.write_text("Title\nBody\n", encoding="utf-8")

    dest = move_to_processed(item_path=item, processed_dir=processed)

    assert dest.exists()
    assert dest.parent == processed
    assert not item.exists()


def test_create_issue_from_queue_is_idempotent_by_queue_id(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=101,
        title="Queue issue",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    record = service.create_issue_from_queue(
        queue_id="dev-1.md",
        queue_path="planning/issue_queue/pending/dev-1.md",
        title="Queue issue",
        body="Body",
        labels=None,
    )
    assert record.source_queue_id == "dev-1.md"

    with pytest.raises(IssueAlreadyExists):
        service.create_issue_from_queue(
            queue_id="dev-1.md",
            queue_path="planning/issue_queue/pending/dev-1.md",
            title="Queue issue (updated title)",
            body="Body",
            labels=None,
        )

    assert mock_github.create_issue.call_count == 1
