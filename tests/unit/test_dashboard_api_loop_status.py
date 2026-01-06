"""Tests for dashboard loop status endpoints and stage computation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


@pytest.fixture(autouse=True)
def mock_automation(monkeypatch):
    """Auto-mock automation functions for all tests to prevent real GitHub API calls."""
    from github_agent_orchestrator.server.dashboard import automation_auto_link, automation_auto_resume
    
    monkeypatch.setattr(
        automation_auto_link,
        "maybe_auto_link_focused_issue_to_pr",
        lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        automation_auto_resume,
        "maybe_auto_resume_copilot_after_rate_limit",
        lambda *args, **kwargs: None
    )


def _dual_patch(monkeypatch: Any, attr_name: str, value: Any) -> None:
    """Patch both dashboard_router and loop_status modules for compatibility.

    Since loop_status functions were extracted from dashboard_router, tests need
    to patch both modules to ensure mocks work correctly regardless of import order.

    Some functions may only exist in loop_status now (if they were moved and not
    imported back into dashboard_router), so we check before patching dashboard_router.
    """
    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    from github_agent_orchestrator.server.dashboard import loop_status

    # Always patch loop_status (where the actual implementation lives)
    monkeypatch.setattr(loop_status, attr_name, value)

    # Also patch dashboard_router if the attribute exists there
    if hasattr(dashboard_router, attr_name):
        monkeypatch.setattr(dashboard_router, attr_name, value)


def test_loop_status_endpoint(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return [
                "planning/issue_queue/pending/dev-1.md",
                "planning/issue_queue/pending/nested/dev-2.md",
            ]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)

    # Provide file contents so /api/loop can read the first line title.
    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        if path == "planning/issue_queue/pending/nested/dev-2.md":
            return "Dev: Two\n\nBody\n", "sha-2"
        raise FileNotFoundError(str(path))

    _dual_patch(monkeypatch, "_get_repo_text_file", fake_get_repo_text_file)

    # No open issues => pending files cannot match any issue => Step B
    _dual_patch(monkeypatch, "_list_open_issues_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())

    loop = client.get("/api/loop").json()
    # Pending development queue files exist and none are promoted to issues => Step B
    assert loop["stage"] == "2a"
    assert loop["activeStep"] == 3
    assert loop["counts"]["pending"] == 2
    assert loop["counts"]["openIssues"] == 0
    assert loop["counts"]["openPullRequests"] == 0
    assert loop["counts"]["unpromotedPending"] == 2
    assert loop["counts"]["pendingDevelopmentWithoutPr"] == 0


def test_loop_status_review_mode_stage_1a_focus_review_issue(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_LOOP_MODE", "review")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_get_pull_request", lambda *_a, **_k: {})

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 201,
                "title": "Review Consumption: 2026-01-05",
                "state": "open",
                "labels": [{"name": "Review Consumption"}],
            }
        ],
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["loopMode"] == "review"
    assert loop["stage"] == "1a"
    assert loop.get("focus", {}).get("kind") == "review"
    assert loop.get("focus", {}).get("issueNumber") == 201


def test_loop_status_review_mode_stage_1b_focus_includes_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_LOOP_MODE", "review")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    def fake_issue_timeline(*_a, **kwargs):
        issue_number = kwargs.get("issue_number")
        # Link the review-consumption issue to PR #5.
        if issue_number == 201:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 5, "pull_request": {}}},
                }
            ]
        return []

    _dual_patch(monkeypatch, "_list_issue_timeline_raw", fake_issue_timeline)
    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "title": "Review intake",
            "html_url": "https://example.com/pr/5",
            "draft": False,
            "mergeable_state": "clean",
            "requested_reviewers": [],
            "requested_teams": [],
        },
    )

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 201,
                "title": "Review Consumption: 2026-01-05",
                "state": "open",
                "labels": [{"name": "Review Consumption"}],
            }
        ],
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["loopMode"] == "review"
    assert loop["stage"] == "1b"
    assert loop.get("focus", {}).get("kind") == "review"
    assert loop.get("focus", {}).get("pullNumber") == 5


def test_loop_status_review_mode_stage_2a_focus_review_queue_item(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_LOOP_MODE", "review")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return ["planning/issue_queue/pending/review-2026-01-05.md"]
        if dir_path in {"planning/issue_queue/processed", "planning/issue_queue/complete"}:
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/review-2026-01-05.md":
            return "Review: One\n\nBody\n", "sha-review-1"
        raise FileNotFoundError(str(path))

    _dual_patch(monkeypatch, "_get_repo_text_file", fake_get_repo_text_file)

    _dual_patch(monkeypatch, "_list_open_issues_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["loopMode"] == "review"
    assert loop["stage"] == "2a"
    assert loop.get("focus", {}).get("queueId") == "review-2026-01-05.md"


def test_loop_status_stage_c_when_issue_exists_but_no_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return ["planning/issue_queue/pending/dev-1.md"]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    _dual_patch(monkeypatch, "_get_repo_text_file", fake_get_repo_text_file)

    # Open issue matches the pending file title, but no PR cross-references exist.
    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["activeStep"] == 4
    assert loop["counts"]["pending"] == 1
    assert loop["counts"]["openIssues"] == 1
    assert loop["counts"]["unpromotedPending"] == 0
    assert loop["counts"]["pendingDevelopmentWithoutPr"] == 1


def test_loop_status_stage_d_when_processed_has_ready_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    _dual_patch(monkeypatch, "_get_repo_text_file", fake_get_repo_text_file)

    # Open issue matches the queue file title.
    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Timeline cross-reference to PR #5.
    _dual_patch(
        monkeypatch,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )

    # PR is open, non-draft, review requested, and conflict-free.
    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2c"
    assert loop["activeStep"] == 5


def test_loop_status_stage_d_when_processed_has_review_requested_event_even_without_requested_reviewers(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    def fake_timeline(*_a, **kwargs):
        # Issue -> PR cross reference.
        if kwargs.get("issue_number") == 101:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 5, "pull_request": {}}},
                }
            ]
        # PR issue timeline contains the explicit review request signal (requested reviewers can be cleared).
        if kwargs.get("issue_number") == 5:
            return [{"event": "review_requested"}]
        return []

    _dual_patch(monkeypatch, "_list_issue_timeline_raw", fake_timeline)

    # PR is open and conflict-free, but requested_reviewers is empty (GitHub clears it after review).
    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2c"
    assert loop["activeStep"] == 5


def test_loop_status_does_not_advance_when_pr_is_wip(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(
        monkeypatch,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )
    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "WIP: Dev: One",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["activeStep"] == 4


def test_loop_status_stage_a_exposes_gap_pr_ready_for_merge(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # No queue artefacts; loop is governed by open gap-analysis issue.
    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path in {
            "planning/issue_queue/pending",
            "planning/issue_queue/processed",
            "planning/issue_queue/complete",
        }:
            return []
        return []

    _dual_patch(monkeypatch, "_list_repo_markdown_files_under", fake_list_repo_md)

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "state": "open",
            }
        ],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Gap-analysis issue timeline cross-references PR #5.
    _dual_patch(
        monkeypatch,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )

    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Gap analysis results",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "1c"
    assert loop["activeStep"] == 2
    assert loop["counts"]["openGapAnalysisIssues"] == 1
    assert loop["counts"]["openGapAnalysisIssuesWithPr"] == 1
    assert loop["counts"]["openGapAnalysisIssuesReadyForReview"] == 1

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "gap"
    assert focus.get("issueNumber") == 42
    assert focus.get("pullNumber") == 5


def test_loop_status_stage_1c_when_gap_pr_is_draft_but_review_requested(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # No queue artefacts; loop is governed by open gap-analysis issue.
    _dual_patch(
        monkeypatch,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [],
    )

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "state": "open",
                "assignees": [],
            }
        ],
    )
    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Gap-analysis issue timeline cross-references PR #5.
    _dual_patch(
        monkeypatch,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )

    # Draft PR with review requested should still count as "ready" for the merge step,
    # because the merge endpoint may mark it ready-for-review before merging.
    _dual_patch(
        monkeypatch,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": True,
            "title": "Add development task: Render components",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "1c"
    assert loop["activeStep"] == 2
    assert loop["counts"]["openGapAnalysisIssues"] == 1
    assert loop["counts"]["openGapAnalysisIssuesWithPr"] == 1
    assert loop["counts"]["openGapAnalysisIssuesReadyForReview"] == 1


def test_loop_status_stage_e_when_open_update_capability_issue_exists(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return ["planning/issue_queue/pending/dev-1.md"]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(
        monkeypatch,
        "_list_repo_markdown_files_under",
        fake_list_repo_md,
    )

    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )

    # Both a development issue and an Update Capability issue are open; capability should win.
    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {"number": 101, "title": "Dev: One", "state": "open"},
            {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "state": "open",
                "labels": [{"name": "Update Capability"}],
            },
        ],
    )

    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    _dual_patch(monkeypatch, "_list_issue_timeline_raw", lambda *_a, **_k: [])

    # The loop status call now fetches the capability issue body to recover the original PR number.
    def fake_github_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/202"):
            return {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "body": "---\n\n<!-- orchestrator:capability-update-from-pr acme/repo#5 -->\n",
            }
        raise AssertionError(f"Unexpected GET url: {url}")

    _dual_patch(monkeypatch, "_github_get_json", fake_github_get_json)

    def fake_get_pull_request(*_a, **kwargs):
        pr_number = kwargs.get("pr_number")
        if pr_number == 5:
            return {
                "number": 5,
                "state": "closed",
                "title": "Add thing",
                "html_url": "https://github.com/acme/repo/pull/5",
            }
        return {}

    _dual_patch(monkeypatch, "_get_pull_request", fake_get_pull_request)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()
    assert loop["stage"] == "3a"
    assert loop["activeStep"] == 6

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "capability"
    assert focus.get("issueNumber") == 202
    assert focus.get("sourcePullNumber") == 5
    assert focus.get("sourceTitle") == "Add thing"


def test_loop_status_stage_g_when_open_update_capability_issue_has_ready_pr(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    _dual_patch(
        monkeypatch,
        "_list_repo_markdown_files_under",
        fake_list_repo_md,
    )

    _dual_patch(monkeypatch, "_get_repo_text_file", lambda *_a, **_k: ("", "sha"))

    _dual_patch(
        monkeypatch,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "state": "open",
                "labels": [{"name": "Update Capability"}],
            }
        ],
    )

    _dual_patch(monkeypatch, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    def fake_timeline(*_a, **kwargs):
        if kwargs.get("issue_number") == 202:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 7, "pull_request": {}}},
                }
            ]
        return []

    _dual_patch(monkeypatch, "_list_issue_timeline_raw", fake_timeline)

    def fake_github_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/202"):
            return {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "body": "x\n<!-- orchestrator:capability-update-from-pr acme/repo#5 -->\n",
            }
        raise AssertionError(f"Unexpected GET url: {url}")

    _dual_patch(monkeypatch, "_github_get_json", fake_github_get_json)

    def fake_get_pull_request(*_a, **kwargs):
        pr_number = kwargs.get("pr_number")
        if pr_number == 7:
            return {
                "number": 7,
                "state": "open",
                "draft": False,
                "requested_reviewers": [{"login": "alice"}],
                "requested_teams": [],
                "mergeable_state": "clean",
                "html_url": "https://github.com/acme/repo/pull/7",
            }
        if pr_number == 5:
            return {
                "number": 5,
                "state": "closed",
                "draft": False,
                "requested_reviewers": [],
                "requested_teams": [],
                "mergeable_state": "clean",
                "title": "Add thing",
                "html_url": "https://github.com/acme/repo/pull/5",
            }
        return {}

    _dual_patch(monkeypatch, "_get_pull_request", fake_get_pull_request)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()
    assert loop["stage"] == "3c"
    assert loop["activeStep"] == 8

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "capability"
    assert focus.get("issueNumber") == 202
    assert focus.get("sourcePullNumber") == 5
    assert focus.get("pullNumber") == 7
