"""Unit tests for orchestrator version inspection and update service."""

from __future__ import annotations

import base64
import tomllib
from pathlib import Path
from typing import Any

import pytest

from backend.app.services.orchestrator_version import (
    LATEST_ORCHESTRATOR_VERSION,
    extract_orchestrator_version,
    is_update_available,
    update_orchestrator_version,
)


class FakeVersionGitHubClient:
    def __init__(self, *, workflow_text: str, branch_exists: bool = False) -> None:
        self.workflow_text = workflow_text
        self.branch_exists = branch_exists
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path_or_url, "kwargs": kwargs})

        if method == "GET" and path_or_url == "/repos/acme/widgets":
            return {"default_branch": "main"}

        if method == "GET" and path_or_url == "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml":
            return {
                "sha": "workflow-sha",
                "content": base64.b64encode(self.workflow_text.encode("utf-8")).decode("utf-8"),
                "encoding": "base64",
            }

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}

        if method == "GET" and path_or_url == "/repos/acme/widgets/git/ref/heads/gao/update-orchestrator-version":
            if self.branch_exists:
                return {"ref": "refs/heads/gao/update-orchestrator-version", "object": {"sha": "old-sha"}}
            return {"message": "Not Found"}

        if method == "POST" and path_or_url == "/repos/acme/widgets/git/refs":
            return {"ref": "refs/heads/gao/update-orchestrator-version"}

        if method == "PATCH" and path_or_url == "/repos/acme/widgets/git/refs/heads/gao/update-orchestrator-version":
            return {"ref": "refs/heads/gao/update-orchestrator-version"}

        if method == "PUT" and path_or_url == "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml":
            return {"content": {"path": ".github/workflows/orchestrator.yml"}}

        if method == "POST" and path_or_url == "/repos/acme/widgets/pulls":
            return {"number": 77, "html_url": "https://example/pr/77", "state": "open"}

        raise AssertionError(f"Unexpected request: {method} {path_or_url}")


def test_extract_orchestrator_version() -> None:
    assert (
        extract_orchestrator_version("pip install github-agent-orchestrator==0.2.0")
        == "0.2.0"
    )
    assert extract_orchestrator_version("pip install github-agent-orchestrator") is None


def test_latest_orchestrator_version_tracks_package_version() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    expected = project.get("version") if isinstance(project, dict) else None
    assert isinstance(expected, str)
    assert LATEST_ORCHESTRATOR_VERSION == expected


def test_is_update_available() -> None:
    assert is_update_available(None, "0.3.1") is True
    assert is_update_available("0.2.9", "0.3.1") is True
    assert is_update_available("0.3.1", "0.3.1") is False
    assert is_update_available("0.4.0", "0.3.1") is False


@pytest.mark.asyncio
async def test_update_orchestrator_version_creates_pr_for_outdated_pin() -> None:
    client = FakeVersionGitHubClient(
        workflow_text="run: pip install github-agent-orchestrator==0.0.1\n",
        branch_exists=False,
    )

    result = await update_orchestrator_version(client, "acme", "widgets")

    assert result["updated"] is True
    assert result["current"] == "0.0.1"
    assert result["latest"] == LATEST_ORCHESTRATOR_VERSION
    assert result["pullRequest"]["number"] == 77

    put_call = [
        call
        for call in client.calls
        if call["method"] == "PUT"
        and call["path"] == "/repos/acme/widgets/contents/.github/workflows/orchestrator.yml"
    ][0]
    updated_workflow = base64.b64decode(put_call["kwargs"]["json"]["content"]).decode("utf-8")
    assert f"github-agent-orchestrator=={LATEST_ORCHESTRATOR_VERSION}" in updated_workflow


@pytest.mark.asyncio
async def test_update_orchestrator_version_noop_when_latest() -> None:
    client = FakeVersionGitHubClient(
        workflow_text=f"run: pip install github-agent-orchestrator=={LATEST_ORCHESTRATOR_VERSION}\n",
        branch_exists=False,
    )

    result = await update_orchestrator_version(client, "acme", "widgets")

    assert result["updated"] is False
    assert result["updateAvailable"] is False
