"""Unit tests for orchestrator run-loop command behavior."""

from __future__ import annotations

from fastapi import HTTPException

from github_agent_orchestrator.orchestrator.commands import run_loop


def test_run_once_stage_2b_refreshes_and_merges_when_ready(
    monkeypatch,
) -> None:
    """If healing is a no-op but refreshed status becomes merge-ready, merge in same run."""

    statuses = iter([
        {"stage": "2b"},
        {"stage": "2c"},
    ])

    def _fake_status(*, settings, active_repo: str, ref: str):  # noqa: ANN001
        _ = settings, active_repo, ref
        return next(statuses)

    def _fake_heal(*, settings, repo: str):  # noqa: ANN001
        _ = settings, repo
        raise HTTPException(status_code=409, detail="No orphaned processed queue artefacts")

    def _fake_merge(*, settings, repo: str):  # noqa: ANN001
        _ = settings, repo
        return {"merged": True, "pullNumber": 99}

    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_status._loop_status_for_repo",
        _fake_status,
    )
    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_actions._heal_orphaned_processed_queue_items",
        _fake_heal,
    )
    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_actions._merge_next_ready_pull_request",
        _fake_merge,
    )

    exit_code, result, message = run_loop.run_once(
        repo="acme/widgets",
        ref="",
        heal_orphans=True,
        auto_approve=True,
    )

    assert exit_code == 0
    assert result == {"merged": True, "pullNumber": 99}
    assert message is None


def test_run_once_stage_2b_refresh_waits_when_manual_approval_required(
    monkeypatch,
) -> None:
    """If merge becomes ready but auto-approve is disabled, return a wait message."""

    statuses = iter([
        {"stage": "2b"},
        {"stage": "2c"},
    ])

    def _fake_status(*, settings, active_repo: str, ref: str):  # noqa: ANN001
        _ = settings, active_repo, ref
        return next(statuses)

    def _fake_heal(*, settings, repo: str):  # noqa: ANN001
        _ = settings, repo
        raise HTTPException(status_code=409, detail="No orphaned processed queue artefacts")

    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_status._loop_status_for_repo",
        _fake_status,
    )
    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_actions._heal_orphaned_processed_queue_items",
        _fake_heal,
    )

    exit_code, result, message = run_loop.run_once(
        repo="acme/widgets",
        ref="",
        heal_orphans=True,
        auto_approve=False,
    )

    assert exit_code == 0
    assert result is None
    assert message == "Waiting for manual approval before merge."


def test_run_once_stage_2b_refresh_stays_noop_when_not_merge_ready(
    monkeypatch,
) -> None:
    """If refresh still is not merge-ready, preserve no-op semantics."""

    statuses = iter([
        {"stage": "2b"},
        {"stage": "2b"},
    ])

    def _fake_status(*, settings, active_repo: str, ref: str):  # noqa: ANN001
        _ = settings, active_repo, ref
        return next(statuses)

    def _fake_heal(*, settings, repo: str):  # noqa: ANN001
        _ = settings, repo
        raise HTTPException(status_code=409, detail="No orphaned processed queue artefacts")

    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_status._loop_status_for_repo",
        _fake_status,
    )
    monkeypatch.setattr(
        "github_agent_orchestrator.server.dashboard.loop_actions._heal_orphaned_processed_queue_items",
        _fake_heal,
    )

    exit_code, result, message = run_loop.run_once(
        repo="acme/widgets",
        ref="",
        heal_orphans=True,
        auto_approve=True,
    )

    assert exit_code == 3
    assert result is None
    assert message == "No orphaned processed queue artefacts"
