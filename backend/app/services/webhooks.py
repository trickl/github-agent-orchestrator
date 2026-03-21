"""Webhook event interpretation helpers.

This module intentionally performs no side effects; it only derives a structured
event summary from incoming GitHub webhook payloads.
"""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_repo_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        full_name = item.get("full_name")
        if isinstance(full_name, str) and full_name:
            names.append(full_name)
    return names


def _handle_workflow_run(action: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    run = _as_dict(payload.get("workflow_run"))
    repository = _as_dict(payload.get("repository"))

    actionable_actions = {"requested", "queued", "in_progress", "completed"}
    should_refresh_status = action in actionable_actions

    return {
        "kind": "workflow_run",
        "action": action,
        "should_refresh_status": should_refresh_status,
        "repository": repository.get("full_name"),
        "run": {
            "id": run.get("id"),
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
            "head_branch": run.get("head_branch"),
            "event": run.get("event"),
        },
        "summary": f"workflow_run:{action or 'unknown'}",
    }


def _handle_installation_repositories(action: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    repositories_added = _as_repo_names(payload.get("repositories_added"))
    repositories_removed = _as_repo_names(payload.get("repositories_removed"))
    installation = _as_dict(payload.get("installation"))

    return {
        "kind": "installation_repositories",
        "action": action,
        "installation_id": installation.get("id"),
        "repositories_added": repositories_added,
        "repositories_removed": repositories_removed,
        "summary": (
            "installation_repositories:"
            f"{action or 'unknown'}"
            f" (+{len(repositories_added)} / -{len(repositories_removed)})"
        ),
    }


def _handle_installation(action: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    installation = _as_dict(payload.get("installation"))
    account = _as_dict(installation.get("account"))
    return {
        "kind": "installation",
        "action": action,
        "installation_id": installation.get("id"),
        "account_login": account.get("login"),
        "summary": f"installation:{action or 'unknown'}",
    }


def _handle_pull_request(action: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    pr = _as_dict(payload.get("pull_request"))
    repository = _as_dict(payload.get("repository"))
    base = _as_dict(pr.get("base"))
    merged = bool(pr.get("merged"))
    should_trigger_run = action == "closed" and merged

    return {
        "kind": "pull_request",
        "action": action,
        "should_trigger_run": should_trigger_run,
        "repository": repository.get("full_name"),
        "pull_request": {
            "number": pr.get("number"),
            "state": pr.get("state"),
            "merged": merged,
            "merge_commit_sha": pr.get("merge_commit_sha"),
            "base_ref": base.get("ref"),
        },
        "summary": f"pull_request:{action or 'unknown'}",
    }


def _handle_ping(payload: dict[str, Any]) -> dict[str, Any]:
    hook = _as_dict(payload.get("hook"))
    return {
        "kind": "ping",
        "zen": payload.get("zen"),
        "hook_id": hook.get("id"),
        "summary": "ping",
    }


def handle_webhook_event(event: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic event summary for supported webhook types."""
    action = payload.get("action") if isinstance(payload.get("action"), str) else None

    if event == "workflow_run":
        return _handle_workflow_run(action, payload)
    if event == "installation_repositories":
        return _handle_installation_repositories(action, payload)
    if event == "installation":
        return _handle_installation(action, payload)
    if event == "pull_request":
        return _handle_pull_request(action, payload)
    if event == "ping":
        return _handle_ping(payload)

    return {
        "kind": "unhandled",
        "event": event,
        "action": action,
        "summary": f"unhandled:{event or 'unknown'}",
    }
