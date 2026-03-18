"""Unit tests for target-state upsert service."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from backend.app.services.target_state import upsert_target_state


class FakeGitHubClient:
    def __init__(self, *, target_exists: bool, config_exists: bool) -> None:
        self.target_exists = target_exists
        self.config_exists = config_exists
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url.endswith("/.orchestrator-agent/state/target_state.md"):
            return {"sha": "target-sha"} if self.target_exists else {"message": "Not Found"}

        if method == "GET" and path_or_url.endswith("/.agent-orchestrator/config.yml"):
            return {"sha": "config-sha"} if self.config_exists else {"message": "Not Found"}

        if method == "PUT" and path_or_url.endswith("/.orchestrator-agent/state/target_state.md"):
            return {"content": {"path": ".orchestrator-agent/state/target_state.md"}}

        if method == "PUT" and path_or_url.endswith("/.agent-orchestrator/config.yml"):
            return {"content": {"path": ".agent-orchestrator/config.yml"}}

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


@pytest.mark.asyncio
async def test_upsert_target_state_creates_target_and_config_when_missing() -> None:
    client = FakeGitHubClient(target_exists=False, config_exists=False)

    result = await upsert_target_state(
        client,
        "acme",
        "widgets",
        "Desired end state",
        branch="main",
    )

    assert result["target_state_created"] is True
    assert result["config_created"] is True

    target_put = [
        c
        for c in client.calls
        if c["method"] == "PUT"
        and c["path"].endswith("/.orchestrator-agent/state/target_state.md")
    ][0]
    target_json = target_put["kwargs"]["json"]
    assert target_json["message"] == "Update target state"
    assert "sha" not in target_json
    assert base64.b64decode(target_json["content"]).decode("utf-8") == "Desired end state"


@pytest.mark.asyncio
async def test_upsert_target_state_updates_target_without_recreating_config() -> None:
    client = FakeGitHubClient(target_exists=True, config_exists=True)

    result = await upsert_target_state(
        client,
        "acme",
        "widgets",
        "Updated state",
        branch="main",
    )

    assert result["target_state_created"] is False
    assert result["config_created"] is False

    target_put = [
        c
        for c in client.calls
        if c["method"] == "PUT"
        and c["path"].endswith("/.orchestrator-agent/state/target_state.md")
    ][0]
    target_json = target_put["kwargs"]["json"]
    assert target_json["sha"] == "target-sha"

    config_puts = [
        c
        for c in client.calls
        if c["method"] == "PUT" and c["path"].endswith("/.agent-orchestrator/config.yml")
    ]
    assert config_puts == []
