"""Unit tests for local orchestrator CLI execution service."""

from __future__ import annotations

import subprocess

from backend.app.services.local_runner import run_orchestrator


def test_run_orchestrator_returns_stdout_stderr_and_exit_code(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        assert args[0] == ["gao", "run", "--repo", "acme/widgets"]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 120
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="[GAO] done\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_orchestrator(
        cli_command="gao",
        owner="acme",
        repo="widgets",
        timeout_seconds=120,
    )

    assert result["status"] == "completed"
    assert result["repo"] == "acme/widgets"
    assert result["stdout"] == "[GAO] done\n"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0
