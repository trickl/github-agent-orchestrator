"""Unit tests for Phase 1A idempotency."""

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


def test_issue_service_idempotency(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=99,
        title="Idempotent",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    service = IssueService(github=mock_github, store=IssueStore(state_file))
    service.create_issue(title="Idempotent", body=None, labels=None)

    with pytest.raises(IssueAlreadyExists):
        service.create_issue(title="Idempotent", body=None, labels=None)

    assert mock_github.create_issue.call_count == 1
