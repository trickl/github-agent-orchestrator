"""Tests for GAO mode-driven runtime and config."""

from __future__ import annotations

from pathlib import Path

import pytest

from gao.config import load_runtime_config
from gao.modes import Mode, should_auto_approve
from gao import run as gao_run


def test_load_runtime_config_defaults_to_semi(tmp_path: Path) -> None:
    config = load_runtime_config(tmp_path)
    assert config.mode == Mode.SEMI


def test_load_runtime_config_reads_mode(tmp_path: Path) -> None:
    (tmp_path / ".orchestrator.yml").write_text("mode: auto\n", encoding="utf-8")
    config = load_runtime_config(tmp_path)
    assert config.mode == Mode.AUTO


def test_load_runtime_config_rejects_invalid_mode(tmp_path: Path) -> None:
    (tmp_path / ".orchestrator.yml").write_text("mode: turbo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mode must be one of"):
        load_runtime_config(tmp_path)


def test_should_auto_approve_only_for_auto_mode() -> None:
    assert should_auto_approve(Mode.MANUAL) is False
    assert should_auto_approve(Mode.SEMI) is False
    assert should_auto_approve(Mode.AUTO) is True


def test_run_single_step_uses_mode_approval_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_once(*, repo: str, ref: str, heal_orphans: bool, auto_approve: bool):
        captured["repo"] = repo
        captured["ref"] = ref
        captured["heal_orphans"] = heal_orphans
        captured["auto_approve"] = auto_approve
        return 0, None, None

    monkeypatch.setattr(gao_run, "run_once", _fake_run_once)

    rc = gao_run.run_single_step(repo="acme/repo", ref="", heal_orphans=False, mode=Mode.SEMI)
    assert rc == 0
    assert captured["auto_approve"] is False

    rc = gao_run.run_single_step(repo="acme/repo", ref="", heal_orphans=False, mode=Mode.AUTO)
    assert rc == 0
    assert captured["auto_approve"] is True


def test_semi_iteration_stops_when_waiting_for_manual_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = iter(
        [
            {"stage": "2c", "stageReason": "development work has an open PR with review requested"},
        ]
    )

    def _fake_status_for_repo(*, repo: str, ref: str):
        return next(statuses)

    def _should_not_run_single_step(*, repo: str, ref: str, heal_orphans: bool, mode: Mode):
        raise AssertionError("run_single_step should not be called in this scenario")

    monkeypatch.setattr(gao_run, "_status_for_repo", _fake_status_for_repo)
    monkeypatch.setattr(gao_run, "run_single_step", _should_not_run_single_step)

    rc = gao_run.run_single_iteration(
        repo="acme/repo",
        ref="",
        heal_orphans=False,
        mode=Mode.SEMI,
        max_steps=5,
        iteration_number=1,
    )

    assert rc == 0


def test_main_defaults_to_semi_mode_when_config_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gao_run, "_resolve_repo", lambda _repo: "acme/repo")

    captured: dict[str, object] = {}

    def _fake_run_single_iteration(
        *,
        repo: str,
        ref: str,
        heal_orphans: bool,
        mode: Mode,
        max_steps: int,
        iteration_number: int,
    ) -> int:
        captured["repo"] = repo
        captured["mode"] = mode
        captured["max_steps"] = max_steps
        captured["iteration_number"] = iteration_number
        return 0

    monkeypatch.setattr(gao_run, "run_single_iteration", _fake_run_single_iteration)

    rc = gao_run.main(["run"])
    assert rc == 0
    assert captured["repo"] == "acme/repo"
    assert captured["mode"] == Mode.SEMI
