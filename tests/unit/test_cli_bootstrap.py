"""Tests for CLI bootstrap helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from github_agent_orchestrator.orchestrator.cli_env import upsert_env_vars
from github_agent_orchestrator.orchestrator.commands.auth_github import handle_auth_github
from github_agent_orchestrator.orchestrator.commands.init import handle_init
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def _settings_no_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OrchestratorSettings:
    monkeypatch.chdir(tmp_path)
    return OrchestratorSettings(require_github_token=False)


def test_upsert_env_vars_preserves_existing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ORCHESTRATOR_DEFAULT_REPO=acme/repo\n", encoding="utf-8")

    upsert_env_vars(
        path=env_path,
        updates={"ORCHESTRATOR_DEFAULT_REPO": "new/repo", "LOG_LEVEL": "DEBUG"},
        overwrite=False,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "ORCHESTRATOR_DEFAULT_REPO=acme/repo" in text
    assert "LOG_LEVEL=DEBUG" in text


def test_upsert_env_vars_overwrites_when_requested(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ORCHESTRATOR_DEFAULT_REPO=acme/repo\n", encoding="utf-8")

    upsert_env_vars(
        path=env_path,
        updates={"ORCHESTRATOR_DEFAULT_REPO": "new/repo"},
        overwrite=True,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "ORCHESTRATOR_DEFAULT_REPO=new/repo" in text


def test_init_creates_env_and_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings_no_token(tmp_path, monkeypatch)

    args = argparse.Namespace(
        repo="acme/repo",
        loop_mode="build",
        env_path=".env",
        force=False,
    )

    rc = handle_init(args, settings)
    assert rc == 0

    env_path = tmp_path / ".env"
    assert env_path.exists()
    text = env_path.read_text(encoding="utf-8")
    assert "ORCHESTRATOR_DEFAULT_REPO=acme/repo" in text
    assert "ORCHESTRATOR_LOOP_MODE=build" in text


def test_auth_github_writes_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings_no_token(tmp_path, monkeypatch)

    args = argparse.Namespace(token="ghp_test", env_path=".env")
    rc = handle_auth_github(args, settings)
    assert rc == 0

    env_path = tmp_path / ".env"
    text = env_path.read_text(encoding="utf-8")
    assert "ORCHESTRATOR_GITHUB_TOKEN=ghp_test" in text
