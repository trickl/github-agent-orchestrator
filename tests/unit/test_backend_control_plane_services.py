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
from backend.app.services.workflows import cancel_latest_run, dispatch_workflow
from backend.app.templates.workflows import render_orchestrator_workflow


class FakeGitHubClient:
    """Minimal async client stub for service-level tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "main"}

        if method == "GET" and path_or_url == "/repos/acme/private":
            return {"default_branch": "master"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/target_state.md":
            return {
                "sha": "target-sha",
                "content": base64.b64encode(b"# Target State\nBuild system\n").decode("utf-8"),
            }

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.orchestrator.yml":
            return {"message": "Not Found"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml":
            return {"message": "Not Found"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/targetstate.md":
            return {"message": "Not Found"}

        if method == "GET" and path_or_url == "/repos/acme/private/contents/.agent-orchestrator/state/target_state.md":
            return {"message": "Resource not accessible by integration"}

        if method == "GET" and path_or_url == "/repos/acme/private/contents/.orchestrator-agent/state/target_state.md":
            return {"message": "Resource not accessible by integration"}

        if method == "GET" and path_or_url == "/repos/acme/private/contents/.agent-orchestrator/state/targetstate.md":
            return {"message": "Resource not accessible by integration"}

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

        if method == "POST" and path_or_url == "/repos/acme/widgets/actions/workflows/orchestrator.yml/dispatches":
            return None

        if method == "POST" and path_or_url == "/repos/acme/widgets/actions/workflows/.github/workflows/orchestrator.yml/dispatches":
            return None

        if method == "POST" and path_or_url == "/repos/acme/widgets/actions/workflows/.github/workflows/pipeline.yaml/dispatches":
            return None

        if method == "GET" and path_or_url == "/repos/acme/widgets/actions/workflows":
            return {
                "workflows": [
                    {"path": ".github/workflows/pipeline.yaml"},
                    {"path": ".github/workflows/release.yml"},
                ]
            }

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
    assert result["initialized_files"][".agent-orchestrator/state/target_state.md"] in {
        "updated",
        "unchanged",
    }
    assert result["initialized_files"][".orchestrator.yml"] == "created"
    assert result["initialized_files"][".github/workflows/orchestrator.yml"] == "created"

    put_paths = [
        call["path"]
        for call in client.calls
        if call["method"] == "PUT" and call["path"].startswith("/repos/acme/widgets/contents/")
    ]
    assert "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml" in put_paths


class FakeInitializeIdempotentClient:
    """Client stub where initialized files already match desired content."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "main"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}

        if method == "POST" and path_or_url == "/repos/acme/widgets/git/refs":
            return {"ref": "refs/heads/gao/init-branch"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/target_state.md":
            return {
                "sha": "target-sha",
                "content": base64.b64encode("# Target\n".encode("utf-8")).decode("utf-8"),
            }

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.orchestrator.yml":
            return {
                "sha": "config-sha",
                "content": base64.b64encode("mode: semi\n".encode("utf-8")).decode("utf-8"),
            }

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml":
            return {
                "sha": "workflow-sha",
                "content": base64.b64encode(render_orchestrator_workflow().encode("utf-8")).decode("utf-8"),
            }

        if method == "POST" and path_or_url == "/repos/acme/widgets/pulls":
            return {"number": 18, "html_url": "https://example/pr/18", "state": "open"}

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_initialize_repo_is_idempotent_when_initialized_files_match() -> None:
    client = FakeInitializeIdempotentClient()

    result = await initialize_repo(
        client,
        "acme",
        "widgets",
        target_state="# Target\n",
        orchestrator_config="mode: semi\n",
        branch_name="gao/init-branch",
        open_pr=True,
    )

    assert result["initialized_files"][".agent-orchestrator/state/target_state.md"] == "unchanged"
    assert result["initialized_files"][".orchestrator.yml"] == "unchanged"
    assert result["initialized_files"][".github/workflows/orchestrator.yml"] == "unchanged"

    content_put_calls = [
        call
        for call in client.calls
        if call["method"] == "PUT" and call["path"].startswith("/repos/acme/widgets/contents/")
    ]
    assert content_put_calls == []


class FakeInitializeDirectClient:
    """Client stub for apply_directly initialization mode."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "main"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}

        if method == "GET" and path_or_url.startswith("/repos/acme/widgets/contents/"):
            return {"message": "Not Found"}

        if method == "PUT" and path_or_url.startswith("/repos/acme/widgets/contents/"):
            return {"content": {"path": path_or_url.split("/contents/")[1]}}

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_initialize_repo_apply_directly_writes_to_default_branch_without_pr() -> None:
    client = FakeInitializeDirectClient()

    result = await initialize_repo(
        client,
        "acme",
        "widgets",
        target_state="# Target\n",
        orchestrator_config="mode: semi\n",
        apply_directly=True,
        open_pr=True,
    )

    assert result["applied_directly"] is True
    assert result["branch"] == "main"
    assert result["opened_pull_request"] is False
    assert "pull_request" not in result

    git_ref_create_calls = [
        call
        for call in client.calls
        if call["method"] == "POST" and call["path"] == "/repos/acme/widgets/git/refs"
    ]
    assert git_ref_create_calls == []


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
    assert result["defaultBranch"] == "main"
    assert result["hasTargetState"] is True
    assert result["status"] == "running"
    assert result["currentStep"] == "Creating PR"
    assert result["latest_run"] is None
    assert result["status_artifact"] is None


@pytest.mark.asyncio
async def test_get_status_handles_target_state_403_as_missing() -> None:
    client = FakeGitHubClient()

    result = await get_status(
        client,
        "acme",
        "private",
    )

    assert result["owner"] == "acme"
    assert result["repo"] == "private"
    assert result["hasTargetState"] is False


class FakeStatusDefaultBranchClient:
    """Client stub to assert status checks use the repository default branch."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "master"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.agent-orchestrator/state/target_state.md":
            return {
                "sha": "target-sha",
                "content": base64.b64encode(b"# Target State\nBuild system\n").decode("utf-8"),
            }

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_get_status_uses_repository_default_branch_for_target_state_reads() -> None:
    client = FakeStatusDefaultBranchClient()

    result = await get_status(
        client,
        "acme",
        "widgets",
    )

    assert result["defaultBranch"] == "master"
    assert result["hasTargetState"] is True

    target_state_calls = [
        call
        for call in client.calls
        if call["method"] == "GET"
        and call["path"] == "/repos/acme/widgets/contents/.agent-orchestrator/state/target_state.md"
    ]
    assert target_state_calls
    assert target_state_calls[0]["kwargs"]["params"]["ref"] == "master"


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


@pytest.mark.asyncio
async def test_dispatch_workflow_dispatches_with_requested_name() -> None:
    client = FakeGitHubClient()

    result = await dispatch_workflow(
        client,
        "acme",
        "widgets",
        workflow_file="orchestrator.yml",
        ref="main",
    )

    assert result["dispatched"] is True
    assert result["workflow"] in {
        "orchestrator.yml",
        ".github/workflows/orchestrator.yml",
    }


class FakeDispatchFallbackClient:
    """Client stub that forces 404 for initial dispatch attempts."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        import httpx

        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "POST" and path_or_url in {
            "/repos/acme/widgets/actions/workflows/orchestrator.yml/dispatches",
            "/repos/acme/widgets/actions/workflows/.github/workflows/orchestrator.yml/dispatches",
            "/repos/acme/widgets/actions/workflows/orchestrator.yaml/dispatches",
            "/repos/acme/widgets/actions/workflows/.github/workflows/orchestrator.yaml/dispatches",
        }:
            request = httpx.Request("POST", f"https://api.github.com{path_or_url}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

        if method == "GET" and path_or_url == "/repos/acme/widgets/actions/workflows":
            return {
                "workflows": [
                    {"path": ".github/workflows/pipeline.yaml"},
                    {"path": ".github/workflows/release.yml"},
                ]
            }

        if method == "POST" and path_or_url == "/repos/acme/widgets/actions/workflows/.github/workflows/pipeline.yaml/dispatches":
            return None

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_dispatch_workflow_falls_back_to_available_workflow_paths() -> None:
    client = FakeDispatchFallbackClient()

    with pytest.raises(ValueError, match="Workflow 'orchestrator.yml' was not found"):
        await dispatch_workflow(
            client,
            "acme",
            "widgets",
            workflow_file="orchestrator.yml",
            ref="main",
        )


class FakeDispatch422Client:
    """Client stub that returns 422 when dispatching a workflow."""

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        import httpx

        if (
            method == "POST"
            and path_or_url == "/repos/acme/widgets/actions/workflows/orchestrator.yml/dispatches"
        ):
            request = httpx.Request("POST", f"https://api.github.com{path_or_url}")
            response = httpx.Response(
                422,
                request=request,
                json={"message": "No ref found for: main"},
            )
            raise httpx.HTTPStatusError("unprocessable", request=request, response=response)

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_dispatch_workflow_surfaces_actionable_422_errors() -> None:
    client = FakeDispatch422Client()

    with pytest.raises(ValueError, match="No ref found for: main"):
        await dispatch_workflow(
            client,
            "acme",
            "widgets",
            workflow_file="orchestrator.yml",
            ref="main",
        )


def test_rendered_orchestrator_workflow_does_not_default_ref_to_main() -> None:
    rendered = render_orchestrator_workflow()
    assert "default: ''" in rendered
    assert "default: main" not in rendered
    assert "repository: trickl/github-agent-orchestrator" in rendered
    assert "python -m pip install --upgrade --no-cache-dir -e ./.orchestrator-runtime" in rendered
    assert "gao run --repo ${{ github.repository }} --heal-orphans" in rendered
    assert "No actionable stage detected; treating as successful no-op." in rendered
