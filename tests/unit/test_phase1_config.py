"""Unit tests for Phase 1 settings loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def test_settings_loads_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCHESTRATOR_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_BASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("AGENT_STATE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "ORCHESTRATOR_GITHUB_TOKEN=test-token",
                "LOG_LEVEL=DEBUG",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings = OrchestratorSettings()

    assert settings.github_token == "test-token"
    assert settings.log_level == "DEBUG"


def test_settings_default_agent_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCHESTRATOR_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_BASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("AGENT_STATE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "ORCHESTRATOR_GITHUB_TOKEN=test-token",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings = OrchestratorSettings()
    assert settings.agent_state_path == Path("agent_state")
    assert settings.issues_state_file == Path("agent_state") / "issues.json"
