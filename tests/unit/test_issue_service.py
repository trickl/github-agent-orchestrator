"""Unit tests for GitHub issue creation (mocked)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from github_agent_orchestrator.orchestrator.github.client import (
    CreatedIssue,
    GitHubClient,
    LinkedPullRequest,
    MergeResult,
    PullRequestDetails,
)
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)


def test_issue_creation_persists_metadata(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=123,
        title="Hello",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    record = service.create_issue(title="Hello", body="Body", labels=["agent", "phase-1"])

    assert record.issue_number == 123
    assert record.title == "Hello"
    assert record.status == "open"

    raw = json.loads(state_file.read_text(encoding="utf-8"))
    assert raw == [
        {
            "repository": "octo-org/octo-repo",
            "issue_number": 123,
            "title": "Hello",
            "created_at": "2025-01-01T00:00:00+00:00",
            "status": "open",
            "assignees": [],
            "source_queue_id": None,
            "source_queue_path": None,
            "linked_pull_requests": [],
            "pr_last_checked_at": None,
            "pr_completion": None,
        }
    ]


def test_issue_creation_is_idempotent_by_title(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=1,
        title="Same title",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    service.create_issue(title="Same title", body=None, labels=None)

    with pytest.raises(IssueAlreadyExists):
        service.create_issue(title="Same title", body=None, labels=None)

    assert mock_github.create_issue.call_count == 1


def test_issue_creation_idempotency_is_scoped_to_repository(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    github_a = Mock(spec=GitHubClient)
    github_a.repository = "octo-org/octo-repo"
    github_a.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=1,
        title="Same title",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    github_b = Mock(spec=GitHubClient)
    github_b.repository = "other-org/other-repo"
    github_b.create_issue.return_value = CreatedIssue(
        repository="other-org/other-repo",
        number=2,
        title="Same title",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)

    service_a = IssueService(github=github_a, store=store)
    service_b = IssueService(github=github_b, store=store)

    service_a.create_issue(title="Same title", body=None, labels=None)
    service_b.create_issue(title="Same title", body=None, labels=None)

    assert github_a.create_issue.call_count == 1
    assert github_b.create_issue.call_count == 1

    raw = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(raw) == 2
    assert {item["repository"] for item in raw} == {"octo-org/octo-repo", "other-org/other-repo"}


def test_assign_issue_updates_local_state_when_present(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=42,
        title="Assignable",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    service.create_issue(title="Assignable", body=None, labels=None)

    mock_github.assign_issue.return_value = ["trickl"]
    updated = service.assign_issue(issue_number=42, assignees=["trickl"])

    assert updated is not None
    assert updated.issue_number == 42
    assert updated.assignees == ["trickl"]
    mock_github.assign_issue.assert_called_once_with(issue_number=42, assignees=["trickl"])

    raw = json.loads(state_file.read_text(encoding="utf-8"))
    assert raw[0]["assignees"] == ["trickl"]


def test_assign_issue_noop_when_not_in_local_store(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"
    mock_github = Mock(spec=GitHubClient)
    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    mock_github.assign_issue.return_value = ["trickl"]
    updated = service.assign_issue(issue_number=999, assignees=["trickl"])
    assert updated is None


def test_assign_issue_to_copilot_updates_local_state_when_present(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=7,
        title="Copilot me",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)
    service.create_issue(title="Copilot me", body=None, labels=None)

    mock_github.assign_issue_with_agent_assignment.return_value = ["copilot-swe-agent[bot]"]
    updated = service.assign_issue_to_copilot(
        issue_number=7,
        copilot_assignee="copilot-swe-agent[bot]",
        target_repo="octo-org/octo-repo",
        base_branch="main",
        custom_instructions="Please add tests",
    )

    assert updated is not None
    assert updated.issue_number == 7
    assert updated.assignees == ["copilot-swe-agent[bot]"]

    mock_github.assign_issue_with_agent_assignment.assert_called_once_with(
        issue_number=7,
        assignees=["copilot-swe-agent[bot]"],
        agent_assignment={
            "target_repo": "octo-org/octo-repo",
            "base_branch": "main",
            "custom_instructions": "Please add tests",
            "custom_agent": "",
            "model": "",
        },
    )


def test_reassign_issue_to_copilot_removes_existing_copilot_then_assigns(tmp_path: Path) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=8,
        title="Reassign me",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)
    service.create_issue(title="Reassign me", body=None, labels=None)

    mock_github.get_issue_assignees.return_value = ["trickl", "Copilot"]
    mock_github.remove_assignees.return_value = ["trickl"]
    mock_github.assign_issue_with_agent_assignment.return_value = ["trickl", "Copilot"]

    updated = service.reassign_issue_to_copilot(
        issue_number=8,
        copilot_assignee="copilot-swe-agent[bot]",
        target_repo="octo-org/octo-repo",
    )

    assert updated is not None
    assert updated.assignees == ["trickl", "Copilot"]

    mock_github.get_issue_assignees.assert_called_once_with(issue_number=8)
    mock_github.remove_assignees.assert_called_once_with(issue_number=8, assignees=["Copilot"])
    mock_github.assign_issue_with_agent_assignment.assert_called_once()


def test_monitor_linked_prs_until_merged_persists_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"
    mock_github.create_issue.return_value = CreatedIssue(
        repository="octo-org/octo-repo",
        number=3,
        title="Track PR",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        status="open",
    )

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)
    service.create_issue(title="Track PR", body=None, labels=None)

    open_pr = LinkedPullRequest(
        number=10,
        url="https://github.com/octo-org/octo-repo/pull/10",
        title="Work in progress",
        state="OPEN",
        is_draft=False,
        merged=False,
        merged_at=None,
        closed_at=None,
        updated_at="2025-01-02T00:00:00Z",
    )
    merged_pr = LinkedPullRequest(
        number=10,
        url="https://github.com/octo-org/octo-repo/pull/10",
        title="Work in progress",
        state="MERGED",
        is_draft=False,
        merged=True,
        merged_at="2025-01-03T00:00:00Z",
        closed_at="2025-01-03T00:00:00Z",
        updated_at="2025-01-03T00:00:00Z",
    )

    mock_github.get_linked_pull_requests.side_effect = [[open_pr], [merged_pr]]

    # Make polling deterministic and fast.
    from github_agent_orchestrator.orchestrator.github import issue_service as issue_service_module

    monotonic_values = iter([0.0, 0.1, 0.2, 0.3])

    def fake_monotonic() -> float:
        return next(monotonic_values)

    monkeypatch.setattr(issue_service_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(issue_service_module.time, "monotonic", fake_monotonic)

    result = service.wait_for_linked_pull_requests_complete(
        issue_number=3,
        poll_interval_seconds=0.01,
        timeout_seconds=1.0,
        require_pull_request=True,
    )

    assert result.completion == "merged"
    assert [pr.number for pr in result.pull_requests] == [10]

    persisted = store.find_by_number(3)
    assert persisted is not None
    assert persisted.pr_completion == "merged"
    assert persisted.linked_pull_requests and persisted.linked_pull_requests[0]["number"] == 10


def test_merge_linked_prs_waits_for_non_draft_then_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "agent_state" / "issues.json"

    mock_github = Mock(spec=GitHubClient)
    mock_github.repository = "octo-org/octo-repo"

    store = IssueStore(state_file)
    service = IssueService(github=mock_github, store=store)

    linked_pr = LinkedPullRequest(
        number=10,
        url="https://github.com/octo-org/octo-repo/pull/10",
        title="Work",
        state="OPEN",
        is_draft=True,
        merged=False,
        merged_at=None,
        closed_at=None,
        updated_at="2025-01-02T00:00:00Z",
    )
    mock_github.get_linked_pull_requests.return_value = [linked_pr]

    draft_details = PullRequestDetails(
        number=10,
        state="open",
        draft=True,
        merged=False,
        mergeable=True,
        mergeable_state="clean",
        head_ref="copilot/branch",
        head_sha="deadbeef",
        head_repo_full_name="octo-org/octo-repo",
        base_ref="main",
        base_repo_full_name="octo-org/octo-repo",
    )
    ready_details = PullRequestDetails(
        number=10,
        state="open",
        draft=False,
        merged=False,
        mergeable=True,
        mergeable_state="clean",
        head_ref="copilot/branch",
        head_sha="deadbeef",
        head_repo_full_name="octo-org/octo-repo",
        base_ref="main",
        base_repo_full_name="octo-org/octo-repo",
    )

    # PR is draft for the first poll, then becomes ready.
    mock_github.get_pull_request.side_effect = [draft_details, ready_details]
    mock_github.mark_pull_request_ready_for_review.return_value = ready_details
    mock_github.merge_pull_request.return_value = MergeResult(merged=True, message="merged")
    mock_github.delete_pull_request_branch.return_value = True

    from github_agent_orchestrator.orchestrator.github import issue_service as issue_service_module

    monotonic_values = iter([0.0, 0.1, 0.2, 0.3])

    def fake_monotonic() -> float:
        return next(monotonic_values)

    monkeypatch.setattr(issue_service_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(issue_service_module.time, "monotonic", fake_monotonic)

    outcomes = service.merge_linked_pull_requests(
        issue_number=3,
        poll_interval_seconds=0.01,
        timeout_seconds=1.0,
        merge_method="squash",
        mark_ready_for_review=True,
        delete_branch=True,
    )

    assert [(o.pull_number, o.merged, o.branch_deleted) for o in outcomes] == [(10, True, True)]
    mock_github.mark_pull_request_ready_for_review.assert_called_once_with(pull_number=10)
    mock_github.merge_pull_request.assert_called_once_with(pull_number=10, merge_method="squash")
