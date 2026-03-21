"""API tests for the lightweight backend control-plane endpoints."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.services.event_log import clear_events
from backend.app.services.run_state import get_repo_run_state
from github_agent_orchestrator import __version__


def _set_required_backend_env(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")


def _reset_event_log() -> None:
    clear_events()


def test_initialize_endpoint(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_initialize(*_args, **_kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "branch": "gao/init-1",
            "opened_pull_request": True,
            "initialized_files": {
                ".agent-orchestrator/state/target_state.md": "created",
                ".orchestrator.yml": "created",
                ".github/workflows/orchestrator.yml": "created",
            },
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "initialize_repo", fake_initialize)

    client = TestClient(app)
    response = client.post(
        "/repos/acme/widgets/initialize",
        json={"target_state": "# Target\n", "orchestrator_config": "mode: semi\n"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "acme"
    assert data["repo"] == "widgets"
    assert data["initialized_files"][".github/workflows/orchestrator.yml"] == "created"


def test_initialize_endpoint_forwards_apply_directly(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    captured: dict[str, object] = {}

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_initialize(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "owner": "acme",
            "repo": "widgets",
            "branch": "main",
            "base_branch": "main",
            "opened_pull_request": False,
            "applied_directly": True,
            "initialized_files": {
                ".agent-orchestrator/state/target_state.md": "created",
                ".orchestrator.yml": "created",
                ".github/workflows/orchestrator.yml": "created",
            },
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "initialize_repo", fake_initialize)

    client = TestClient(app)
    response = client.post(
        "/repos/acme/widgets/initialize",
        json={
            "target_state": "# Target\n",
            "orchestrator_config": "mode: semi\n",
            "open_pr": False,
            "apply_directly": True,
        },
    )

    assert response.status_code == 200
    assert captured["open_pr"] is False
    assert captured["apply_directly"] is True


def test_upsert_target_state_endpoint(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_upsert(*_args, **_kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "branch": "main",
            "target_state_path": ".agent-orchestrator/state/target_state.md",
            "target_state_updated": True,
            "target_state_created": True,
            "config_path": ".agent-orchestrator/config.yml",
            "config_created": True,
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "upsert_target_state", fake_upsert)

    client = TestClient(app)
    response = client.post(
        "/repos/acme/widgets/target-state",
        json={"content": "User-defined target system description"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "acme"
    assert payload["repo"] == "widgets"
    assert payload["target_state_updated"] is True


def test_update_orchestrator_endpoint(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_update(*_args, **_kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "branch": "gao/update-orchestrator-version",
            "baseBranch": "main",
            "workflowPath": ".github/workflows/orchestrator.yml",
            "current": "0.2.0",
            "latest": "0.3.1",
            "updateAvailable": True,
            "updated": True,
            "pullRequest": {"number": 42, "url": "https://example/pr/42", "state": "open"},
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "update_orchestrator_version", fake_update)

    client = TestClient(app)
    response = client.post(
        "/repos/acme/widgets/update-orchestrator",
        json={},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] is True
    assert payload["latest"] == "0.3.1"
    assert payload["pullRequest"]["number"] == 42


def test_start_stop_status_and_list_repos_endpoints(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.actions as actions_routes
    import backend.app.routes.repos as repos_routes
    import backend.app.routes.status as status_routes

    actions_routes.get_settings.cache_clear()
    repos_routes.get_settings.cache_clear()
    status_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_dispatch(*_args, **_kwargs):
        return {"dispatched": True, "workflow": "orchestrator.yml", "ref": "main"}

    async def fake_cancel(*_args, **_kwargs):
        return {"canceled": True, "run_id": 1001}

    async def fake_status(*_args, **_kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "hasTargetState": True,
            "status": "idle",
            "currentStep": None,
            "workflow_file": "orchestrator.yml",
            "workflow": {
                "name": "orchestrator.yml",
                "orchestratorVersion": {
                    "current": "0.2.0",
                    "latest": "0.3.1",
                    "updateAvailable": True,
                },
            },
            "latest_run": {"id": 1001, "status": "completed", "conclusion": "success"},
            "status_artifact": {"stage": "3a", "active_issue_ids": [42], "active_pr_ids": [77]},
            "active_issue_ids": [42],
            "active_pr_ids": [77],
        }

    async def fake_repos(*_args, **_kwargs):
        return ["acme/widgets"]

    monkeypatch.setattr(actions_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(status_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)

    monkeypatch.setattr(actions_routes, "dispatch_workflow", fake_dispatch)
    monkeypatch.setattr(actions_routes, "cancel_latest_run", fake_cancel)
    monkeypatch.setattr(status_routes, "get_status", fake_status)
    monkeypatch.setattr(repos_routes, "list_accessible_repositories", fake_repos)

    client = TestClient(app)

    start_response = client.post("/repos/acme/widgets/start", json={"ref": "main"})
    assert start_response.status_code == 200
    assert start_response.json()["dispatched"] is True

    stop_response = client.post("/repos/acme/widgets/stop", json={})
    assert stop_response.status_code == 200
    assert stop_response.json()["canceled"] is True

    status_response = client.get("/repos/acme/widgets/status")
    assert status_response.status_code == 200
    assert status_response.json()["latest_run"]["id"] == 1001
    assert status_response.json()["hasTargetState"] is True
    assert status_response.json()["workflow"]["orchestratorVersion"]["latest"] == "0.3.1"

    repos_response = client.get("/repos")
    assert repos_response.status_code == 200
    assert repos_response.json() == ["acme/widgets"]


def test_start_endpoint_uses_repo_default_branch_when_ref_omitted(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.actions as actions_routes

    actions_routes.get_settings.cache_clear()

    class _Client:
        async def request(self, method, path_or_url, **_kwargs):
            if method == "GET" and path_or_url == "/repos/acme/widgets":
                return {"default_branch": "master"}
            raise AssertionError(f"Unexpected request: {method} {path_or_url}")

    async def fake_create_client(*_args, **_kwargs):
        return _Client()

    async def fake_dispatch(*_args, **kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "workflow": "orchestrator.yml",
            "ref": kwargs["ref"],
            "dispatched": True,
        }

    monkeypatch.setattr(actions_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(actions_routes, "dispatch_workflow", fake_dispatch)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/start", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["dispatched"] is True
    assert payload["ref"] == "master"


def test_development_prs_endpoint(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_development_prs(*_args, **_kwargs):
        return [
            {
                "title": "Implement API layer",
                "url": "https://example/pr/10",
                "createdAt": "2026-03-18T10:10:00Z",
            }
        ]

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "list_development_pull_requests", fake_development_prs)

    client = TestClient(app)
    response = client.get("/repos/acme/widgets/development-prs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Implement API layer"


def test_dispatch_workflow_run_endpoint(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_dispatch(*_args, **_kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "workflow": "orchestrator.yml",
            "ref": "main",
            "dispatched": True,
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "dispatch_workflow", fake_dispatch)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/run", json={"ref": "main"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dispatched"
    assert payload["repo"] == "acme/widgets"
    assert payload["dispatched"] is True
    assert payload["workflow"] == "orchestrator.yml"
    assert payload["ref"] == "main"


def test_dispatch_workflow_run_endpoint_uses_repo_default_branch_when_ref_omitted(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    class _Client:
        async def request(self, method, path_or_url, **_kwargs):
            if method == "GET" and path_or_url == "/repos/acme/widgets":
                return {"default_branch": "master"}
            raise AssertionError(f"Unexpected request: {method} {path_or_url}")

    async def fake_create_client(*_args, **_kwargs):
        return _Client()

    async def fake_dispatch(*_args, **kwargs):
        return {
            "owner": "acme",
            "repo": "widgets",
            "workflow": "orchestrator.yml",
            "ref": kwargs["ref"],
            "dispatched": True,
        }

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "dispatch_workflow", fake_dispatch)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/run", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dispatched"
    assert payload["repo"] == "acme/widgets"
    assert payload["dispatched"] is True
    assert payload["workflow"] == "orchestrator.yml"
    assert payload["ref"] == "master"


def test_dispatch_workflow_run_endpoint_bootstraps_missing_workflow(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    calls = {"dispatch": 0, "bootstrap": 0}

    async def fake_dispatch(*_args, **_kwargs):
        calls["dispatch"] += 1
        if calls["dispatch"] == 1:
            raise ValueError(
                "No GitHub Actions workflows found in target repository 'acme/widgets'. "
                "The control plane dispatches workflows from the selected target repository "
                "(not the github-agent-orchestrator control-plane repository). "
                "Add a workflow file under '.github/workflows' in the target repository "
                "and enable workflow_dispatch."
            )
        return {
            "owner": "acme",
            "repo": "widgets",
            "workflow": "orchestrator.yml",
            "ref": "main",
            "dispatched": True,
        }

    async def fake_ensure_workflow(*_args, **_kwargs):
        calls["bootstrap"] += 1
        return {"status": "created"}

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "dispatch_workflow", fake_dispatch)
    monkeypatch.setattr(repos_routes, "ensure_orchestrator_workflow", fake_ensure_workflow)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/run", json={"ref": "main"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dispatched"
    assert payload["repo"] == "acme/widgets"
    assert payload["dispatched"] is True
    assert payload["workflow"] == "orchestrator.yml"
    assert payload["ref"] == "main"
    assert calls["bootstrap"] == 1
    assert calls["dispatch"] == 2


def test_dispatch_workflow_run_endpoint_returns_actionable_error_on_bootstrap_403(
    monkeypatch,
) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_dispatch(*_args, **_kwargs):
        raise ValueError(
            "No GitHub Actions workflows found in target repository 'acme/widgets'. "
            "The control plane dispatches workflows from the selected target repository "
            "(not the github-agent-orchestrator control-plane repository). "
            "Add a workflow file under '.github/workflows' in the target repository "
            "and enable workflow_dispatch."
        )

    async def fake_ensure_workflow(*_args, **_kwargs):
        raise ValueError(
            "Cannot create or update '.github/workflows/orchestrator.yml' in target repository "
            "'acme/widgets' because the GitHub App lacks required permissions. "
            "Grant the app 'Contents: Read and write' and 'Workflows: Read and write', "
            "then reinstall or refresh app access for the repository and retry."
        )

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "dispatch_workflow", fake_dispatch)
    monkeypatch.setattr(repos_routes, "ensure_orchestrator_workflow", fake_ensure_workflow)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/run", json={"ref": "main"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "lacks required permissions" in detail
    assert "Contents: Read and write" in detail
    assert "Workflows: Read and write" in detail


def test_dispatch_workflow_run_endpoint_persists_failure_reason_in_run_state(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.repos as repos_routes

    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        return object()

    async def fake_dispatch(*_args, **_kwargs):
        raise ValueError("No ref found for: main")

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)
    monkeypatch.setattr(repos_routes, "dispatch_workflow", fake_dispatch)

    client = TestClient(app)
    response = client.post("/repos/acme/widgets/run", json={"ref": "main"})

    assert response.status_code == 502
    run_state = get_repo_run_state("acme/widgets")
    assert run_state.status == "error"
    assert isinstance(run_state.current_step, str)
    assert "Workflow dispatch failed:" in run_state.current_step
    assert "No ref found for: main" in run_state.current_step


def test_webhook_endpoint_accepts_valid_signature(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    _reset_event_log()

    import backend.app.routes.webhooks as webhook_routes

    webhook_routes.get_settings.cache_clear()

    client = TestClient(app)
    body = (
        '{'
        '"action":"queued",'
        '"repository":{"full_name":"acme/widgets"},'
        '"workflow_run":{' 
        '"id":123,'
        '"name":"orchestrator",'
        '"status":"queued",'
        '"conclusion":null,'
        '"html_url":"https://example/run/123",'
        '"head_branch":"main",'
        '"event":"workflow_dispatch"'
        '}'
        '}'
    )
    secret = "test-webhook-secret"
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={digest}",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-123",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["event"] == "workflow_run"
    assert payload["action"] == "queued"
    assert payload["handled"]["kind"] == "workflow_run"
    assert payload["handled"]["should_refresh_status"] is True
    assert payload["handled"]["repository"] == "acme/widgets"
    assert payload["handled"]["run"]["id"] == 123


def test_webhook_endpoint_rejects_invalid_signature(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    _reset_event_log()

    import backend.app.routes.webhooks as webhook_routes

    webhook_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/webhooks/github",
        content='{"action":"queued"}',
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=bad-signature",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-123",
        },
    )
    assert response.status_code == 401
    assert "Invalid webhook signature" in response.json()["detail"]


def test_webhook_endpoint_requires_secret(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    _reset_event_log()

    import backend.app.routes.webhooks as webhook_routes

    webhook_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/webhooks/github",
        content='{"action":"queued"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert "GITHUB_WEBHOOK_SECRET" in response.json()["detail"]


def test_webhook_endpoint_handles_installation_repositories_event(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    _reset_event_log()

    import backend.app.routes.webhooks as webhook_routes

    webhook_routes.get_settings.cache_clear()

    client = TestClient(app)
    body = (
        '{'
        '"action":"added",'
        '"installation":{"id":99},'
        '"repositories_added":[{"full_name":"acme/widgets"}],'
        '"repositories_removed":[{"full_name":"acme/legacy"}]'
        '}'
    )
    secret = "test-webhook-secret"
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={digest}",
            "X-GitHub-Event": "installation_repositories",
            "X-GitHub-Delivery": "delivery-456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"]["kind"] == "installation_repositories"
    assert payload["handled"]["installation_id"] == 99
    assert payload["handled"]["repositories_added"] == ["acme/widgets"]
    assert payload["handled"]["repositories_removed"] == ["acme/legacy"]


def test_cors_preflight_allows_github_pages_origin(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://trickl.github.io")

    client = TestClient(app)
    response = client.options(
        "/repos",
        headers={
            "Origin": "https://trickl.github.io",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://trickl.github.io"


def test_version_endpoint_includes_version_and_git_sha(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123def456")
    monkeypatch.setenv("BUILD_TIME_UTC", "2026-03-19T00:00:00+00:00")

    client = TestClient(app)
    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "control-plane-backend"
    assert payload["version"] == __version__
    assert payload["versionSource"] == "pyproject-toml"
    assert payload["gitSha"] == "abc123def456"
    assert payload["buildTimeUtc"] == "2026-03-19T00:00:00+00:00"


def test_version_endpoint_uses_unknown_git_sha_when_not_available(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("SOURCE_VERSION", raising=False)

    client = TestClient(app)
    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == __version__
    assert payload["versionSource"] == "pyproject-toml"
    assert payload["gitSha"] == "unknown"
    assert isinstance(payload["buildTimeUtc"], str)


def test_recent_webhook_events_endpoint_returns_latest_entries(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)
    _reset_event_log()

    import backend.app.routes.webhooks as webhook_routes

    webhook_routes.get_settings.cache_clear()

    client = TestClient(app)
    secret = "test-webhook-secret"

    body1 = '{"action":"queued"}'
    digest1 = hmac.new(secret.encode("utf-8"), body1.encode("utf-8"), hashlib.sha256).hexdigest()
    response1 = client.post(
        "/webhooks/github",
        content=body1,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={digest1}",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-1",
        },
    )
    assert response1.status_code == 200

    body2 = '{"action":"completed"}'
    digest2 = hmac.new(secret.encode("utf-8"), body2.encode("utf-8"), hashlib.sha256).hexdigest()
    response2 = client.post(
        "/webhooks/github",
        content=body2,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={digest2}",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-2",
        },
    )
    assert response2.status_code == 200

    recent = client.get("/webhooks/events/recent", params={"limit": 1})
    assert recent.status_code == 200
    payload = recent.json()
    assert payload["count"] == 1
    assert payload["events"][0]["delivery_id"] == "delivery-2"


def test_github_app_install_url_endpoint_uses_slug(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_APP_SLUG", "github-agent-orchestrator")

    import backend.app.routes.auth as auth_routes

    auth_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/auth/github-app/install-url")

    assert response.status_code == 200
    assert (
        response.json()["installUrl"]
        == "https://github.com/apps/github-agent-orchestrator/installations/new"
    )


def test_github_app_install_url_endpoint_falls_back_to_settings_page(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.delenv("GITHUB_APP_INSTALL_URL", raising=False)
    monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)

    import backend.app.routes.auth as auth_routes

    auth_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/auth/github-app/install-url")

    assert response.status_code == 200
    assert response.json()["installUrl"] == "https://github.com/settings/installations"


def test_github_app_install_url_endpoint_accepts_full_app_url_in_slug_env(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_APP_SLUG", "https://github.com/apps/github-agent-orchestrator")

    import backend.app.routes.auth as auth_routes

    auth_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/auth/github-app/install-url")

    assert response.status_code == 200
    assert (
        response.json()["installUrl"]
        == "https://github.com/apps/github-agent-orchestrator/installations/new"
    )


def test_github_app_install_url_endpoint_accepts_apps_path_in_slug_env(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_APP_SLUG", "github.com/apps/github-agent-orchestrator/installations/new")

    import backend.app.routes.auth as auth_routes

    auth_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/auth/github-app/install-url")

    assert response.status_code == 200
    assert (
        response.json()["installUrl"]
        == "https://github.com/apps/github-agent-orchestrator/installations/new"
    )


def test_repos_endpoint_requires_auth_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "oauth-client-id")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "oauth-client-secret")
    monkeypatch.setenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "https://github-agent-orchestrator.onrender.com/auth/github/callback",
    )
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-session-secret")

    import backend.app.routes.auth as auth_routes
    import backend.app.routes.repos as repos_routes

    auth_routes.get_settings.cache_clear()
    repos_routes.get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/repos")

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_repos_endpoint_returns_actionable_key_error(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.auth as auth_routes
    import backend.app.routes.repos as repos_routes

    auth_routes.get_settings.cache_clear()
    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        raise RuntimeError("Could not parse the provided public key.")

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)

    client = TestClient(app)
    response = client.get("/repos")

    assert response.status_code == 502
    assert "GitHub App key is invalid" in response.json()["detail"]


def test_repos_endpoint_returns_empty_list_when_no_installations(monkeypatch) -> None:
    _set_required_backend_env(monkeypatch)

    import backend.app.routes.auth as auth_routes
    import backend.app.routes.repos as repos_routes

    auth_routes.get_settings.cache_clear()
    repos_routes.get_settings.cache_clear()

    async def fake_create_client(*_args, **_kwargs):
        raise RuntimeError("No GitHub App installations available")

    monkeypatch.setattr(repos_routes, "create_github_client", fake_create_client)

    client = TestClient(app)
    response = client.get("/repos")

    assert response.status_code == 200
    assert response.json() == []


def test_settings_normalize_wrapped_private_key(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        '"-----BEGIN PRIVATE KEY-----\\nTESTKEY\\n-----END PRIVATE KEY-----"',
    )

    settings = Settings()
    assert settings.github_app_private_key.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert settings.github_app_private_key.endswith("\n-----END PRIVATE KEY-----")


def test_settings_reject_non_pem_private_key(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_REQUIRE_AUTH", "false")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "not-a-pem-key")

    with pytest.raises(ValueError, match="must be a PEM private key"):
        Settings()
