"""Unit tests for lightweight backend control-plane services."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from backend.app.services.event_log import append_event, clear_events, get_recent_events
from backend.app.services.install import initialize_repo
from backend.app.services.run_state import set_repo_run_state
from backend.app.services.status import get_status, list_development_pull_requests
from backend.app.services.webhooks import handle_webhook_event
from backend.app.services.workflows import cancel_latest_run


class FakeGitHubClient:
    """Minimal async client stub for service-level tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "main"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/target_state.md":
            return {
                "sha": "target-sha",
                "content": base64.b64encode(b"# Target State\nBuild system\n").decode("utf-8"),
            }

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/targetstate.md":
            return {"message": "Not Found"}

        if method == "POST" and path_or_url == "/repos/acme/widgets/git/refs":
            return {"ref": "refs/heads/gao/init-branch"}

        if method == "PUT" and path_or_url.startswith("/repos/acme/widgets/contents/"):
            return {"content": {"path": path_or_url.split("/contents/")[1]}}

        if method == "POST" and path_or_url == "/repos/acme/widgets/pulls":
            return {"number": 17, "html_url": "https://example/pr/17", "state": "open"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/pulls":
            return [
                {
                    "title": "Implement API layer",
                    "html_url": "https://example/pr/10",
                    "created_at": "2026-03-18T10:10:00Z",
                },
                {
                    "title": "Gap Analysis: next task",
                    "html_url": "https://example/pr/9",
                    "created_at": "2026-03-18T10:05:00Z",
                },
            ]

        if (
            method == "GET"
            and path_or_url == "/repos/acme/widgets/actions/workflows/orchestrator.yml/runs"
        ):
            params = kwargs.get("params", {})
            if params.get("status") == "in_progress":
                return {"workflow_runs": []}
            return {"workflow_runs": []}

        if method == "POST" and path_or_url == "/repos/acme/widgets/actions/runs/999/cancel":
            return None

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")

@pytest.mark.asyncio
async def test_initialize_repo_creates_branch_files_and_pr() -> None:
    client = FakeGitHubClient()

    result = await initialize_repo(
        client,
        "acme",
        "widgets",
        target_state="# Target\n",
        orchestrator_config="mode: semi\n",
        branch_name="gao/init-branch",
        open_pr=True,
    )

    assert result["branch"] == "gao/init-branch"
    assert result["base_branch"] == "main"
    assert result["opened_pull_request"] is True
    assert result["pull_request"]["number"] == 17


@pytest.mark.asyncio
async def test_cancel_latest_run_returns_noop_when_nothing_running() -> None:
    client = FakeGitHubClient()

    result = await cancel_latest_run(
        client,
        "acme",
        "widgets",
        workflow_file="orchestrator.yml",
    )

    assert result["canceled"] is False
    assert "No in-progress" in str(result["reason"])


@pytest.mark.asyncio
async def test_get_status_includes_latest_run_and_parsed_artifact() -> None:
    client = FakeGitHubClient()
    set_repo_run_state("acme/widgets", status="running", current_step="Creating PR")

    result = await get_status(
        client,
        "acme",
        "widgets",
    )

    assert result["owner"] == "acme"
    assert result["repo"] == "widgets"
    assert result["hasTargetState"] is True
    assert result["status"] == "running"
    assert result["currentStep"] == "Creating PR"
    assert result["latest_run"] is None
    assert result["status_artifact"] is None


@pytest.mark.asyncio
async def test_list_development_pull_requests_filters_meta_prs() -> None:
    client = FakeGitHubClient()

    result = await list_development_pull_requests(
        client,
        "acme",
        "widgets",
    )

    assert len(result) == 1
    assert result[0]["title"] == "Implement API layer"


def test_handle_webhook_event_workflow_run() -> None:
    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/widgets"},
        "workflow_run": {
            "id": 101,
            "name": "orchestrator",
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example/run/101",
            "head_branch": "main",
            "event": "workflow_dispatch",
        },
    }

    handled = handle_webhook_event("workflow_run", payload)
    assert handled["kind"] == "workflow_run"
    assert handled["should_refresh_status"] is True
    assert handled["repository"] == "acme/widgets"
    assert handled["run"]["id"] == 101
    assert handled["run"]["conclusion"] == "success"


def test_handle_webhook_event_unhandled() -> None:
    handled = handle_webhook_event("issue_comment", {"action": "created"})
    assert handled["kind"] == "unhandled"
    assert handled["event"] == "issue_comment"
    assert handled["action"] == "created"


def test_event_log_returns_most_recent_first() -> None:
    clear_events()
    append_event({"delivery_id": "d1", "event": "workflow_run"})
    append_event({"delivery_id": "d2", "event": "workflow_run"})

    recent = get_recent_events(limit=2)
    assert len(recent) == 2
    assert recent[0]["delivery_id"] == "d2"
    assert recent[1]["delivery_id"] == "d1"
    assert "received_at" in recent[0]
