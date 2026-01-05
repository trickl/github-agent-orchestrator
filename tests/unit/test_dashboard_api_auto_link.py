"""Tests for dashboard auto-link functionality."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def test_loop_status_auto_links_focused_issue_to_likely_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR", "true")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # Processed development item exists, and its issue is open (stage 2b).
    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **kwargs: (
            ["planning/issue_queue/processed/restore-drag-and-drop.md"]
            if kwargs.get("dir_path") == "planning/issue_queue/processed"
            else []
        ),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Restore drag-and-drop\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 184, "title": "Restore drag-and-drop", "state": "open"}],
    )

    # There is an open PR, but the issue has no cross-reference to it yet.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_pull_requests_raw",
        lambda *_a, **_k: [
            {
                "number": 185,
                "state": "open",
                "title": "Restore drag-and-drop",
                "draft": True,
                "user": {"login": "copilot-swe-agent"},
            }
        ],
    )
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])

    # PR body does not yet mention `Fixes #184`.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {"number": 185, "body": "Implementation details\n"},
    )

    patched: dict[str, object] = {}

    def fake_patch_json(_settings, *, url: str, payload: dict[str, object]):
        patched["url"] = url
        patched["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["focus"]["issueNumber"] == 184
    assert loop["focus"]["pullNumber"] is None

    assert str(patched.get("url", "")).endswith("/repos/acme/repo/pulls/185")
    payload = patched.get("payload")
    assert isinstance(payload, dict)
    body = payload.get("body")
    assert isinstance(body, str)
    assert "Fixes #184" in body
    # We prepend the closing keyword to avoid getting swallowed by unclosed Markdown fences.
    assert body.lstrip().startswith("Fixes #184")


def test_loop_status_auto_links_when_pr_branch_is_copilot_prefixed(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR", "true")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # Processed development item exists, and its issue is open (stage 2b).
    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **kwargs: (
            ["planning/issue_queue/processed/restore-drag-and-drop.md"]
            if kwargs.get("dir_path") == "planning/issue_queue/processed"
            else []
        ),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Restore drag-and-drop\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 184, "title": "Restore drag-and-drop", "state": "open"}],
    )

    # The PR author login is not Copilot, but the branch name indicates Copilot created it.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_pull_requests_raw",
        lambda *_a, **_k: [
            {
                "number": 185,
                "state": "open",
                "title": "Restore drag-and-drop",
                "draft": True,
                "user": {"login": "alice"},
                "head": {"ref": "copilot/restore-drag-and-drop"},
            }
        ],
    )
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])

    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {"number": 185, "body": "Implementation details\n"},
    )

    patched: dict[str, object] = {}

    def fake_patch_json(_settings, *, url: str, payload: dict[str, object]):
        patched["url"] = url
        patched["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["focus"]["issueNumber"] == 184
    assert loop["focus"]["pullNumber"] is None

    assert str(patched.get("url", "")).endswith("/repos/acme/repo/pulls/185")
    payload = patched.get("payload")
    assert isinstance(payload, dict)
    body = payload.get("body")
    assert isinstance(body, str)
    assert "Fixes #184" in body
    assert body.lstrip().startswith("Fixes #184")


def test_auto_link_ignores_closing_keyword_inside_unclosed_code_fence(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR", "true")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **kwargs: (
            ["planning/issue_queue/processed/restore-drag-and-drop.md"]
            if kwargs.get("dir_path") == "planning/issue_queue/processed"
            else []
        ),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Restore drag-and-drop\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 184, "title": "Restore drag-and-drop", "state": "open"}],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_pull_requests_raw",
        lambda *_a, **_k: [
            {
                "number": 185,
                "state": "open",
                "title": "Restore drag-and-drop",
                "draft": True,
                "user": {"login": "copilot-swe-agent"},
            }
        ],
    )
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])

    # PR body contains `Fixes #184` but only inside an unclosed fenced code block.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {"number": 185, "body": "```\nFixes #184\n"},
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_comments_raw",
        lambda *_a, **_k: [],
    )

    patched: dict[str, object] = {}

    def fake_patch_json(_settings, *, url: str, payload: dict[str, object]):
        patched["url"] = url
        patched["payload"] = payload
        return {"ok": True}

    posted: dict[str, object] = {}

    def fake_post_json(_settings, *, url: str, payload: dict[str, object]):
        posted["url"] = url
        posted["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)
    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    _loop = client.get("/api/loop").json()

    assert str(patched.get("url", "")).endswith("/repos/acme/repo/pulls/185")
    payload = patched.get("payload")
    assert isinstance(payload, dict)
    body = payload.get("body")
    assert isinstance(body, str)
    assert body.lstrip().startswith("Fixes #184")

    # A transparency comment is also posted.
    assert str(posted.get("url", "")).endswith("/repos/acme/repo/issues/185/comments")
    posted_payload = posted.get("payload")
    assert isinstance(posted_payload, dict)
    posted_body = posted_payload.get("body")
    assert isinstance(posted_body, str)
    assert "auto-linked" in posted_body.lower()
