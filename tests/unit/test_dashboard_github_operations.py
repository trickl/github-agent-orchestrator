"""Tests for dashboard GitHub operations memory-safety behavior."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard import github_operations


def test_list_repo_markdown_files_under_reuses_tree_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"head": 0, "tree_sha": 0, "tree": 0}

    monkeypatch.setattr(github_operations, "get_default_branch", lambda *_a, **_k: "main")

    def _fake_head(*_a, **_k):
        calls["head"] += 1
        return "commit-sha"

    def _fake_tree_sha(*_a, **_k):
        calls["tree_sha"] += 1
        return "tree-sha"

    def _fake_tree(*_a, **_k):
        calls["tree"] += 1
        return [
            {"type": "blob", "path": ".agent-orchestrator/issue_queue/pending/dev-1.md"},
            {"type": "blob", "path": ".agent-orchestrator/issue_queue/processed/dev-1.md"},
            {"type": "blob", "path": ".agent-orchestrator/issue_queue/complete/dev-1.md"},
        ]

    monkeypatch.setattr(github_operations, "get_branch_head_commit_sha", _fake_head)
    monkeypatch.setattr(github_operations, "get_commit_tree_sha", _fake_tree_sha)
    monkeypatch.setattr(github_operations, "get_repo_tree_recursive", _fake_tree)

    settings = ServerSettings()
    tree_cache: dict[str, Any] = {}

    pending = github_operations.list_repo_markdown_files_under(
        settings=settings,
        repository="acme/repo",
        dir_path=".agent-orchestrator/issue_queue/pending",
        ref="main",
        tree_cache=tree_cache,
    )
    processed = github_operations.list_repo_markdown_files_under(
        settings=settings,
        repository="acme/repo",
        dir_path=".agent-orchestrator/issue_queue/processed",
        ref="main",
        tree_cache=tree_cache,
    )
    complete = github_operations.list_repo_markdown_files_under(
        settings=settings,
        repository="acme/repo",
        dir_path=".agent-orchestrator/issue_queue/complete",
        ref="main",
        tree_cache=tree_cache,
    )

    assert pending == [".agent-orchestrator/issue_queue/pending/dev-1.md"]
    assert processed == [".agent-orchestrator/issue_queue/processed/dev-1.md"]
    assert complete == [".agent-orchestrator/issue_queue/complete/dev-1.md"]
    assert calls == {"head": 1, "tree_sha": 1, "tree": 1}


def test_download_workflow_job_logs_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        status_code = 200
        headers = {"Content-Length": "5000000"}

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

        def iter_content(self, chunk_size: int):  # pragma: no cover - should not be reached
            _ = chunk_size
            yield b""

    monkeypatch.setattr(github_operations.requests, "get", lambda *_a, **_k: _FakeResponse())

    with pytest.raises(HTTPException, match="too large") as exc_info:
        github_operations.download_workflow_job_logs(
            ServerSettings(),
            repository="acme/repo",
            job_id=123,
            max_bytes=2_000_000,
        )

    assert exc_info.value.status_code == 413
