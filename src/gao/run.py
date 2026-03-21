"""Mode-driven CLI entrypoint for GitHub Agent Orchestrator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from gao.config import load_runtime_config
from gao.modes import Mode, should_auto_approve
from github_agent_orchestrator.orchestrator.commands.run_loop import MERGE_STAGES, run_once
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.loop_status import _loop_status_for_repo

_NO_WORK_STAGE_REASON = "no pending/processed artefacts"


def _log(message: str) -> None:
    print(f"[GAO] {message}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gao",
        description="GitHub Agent Orchestrator mode-driven runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run", help="Run orchestrator in configured execution mode")
    run_cmd.add_argument("--repo", default="", help="Target repository in the form owner/repo")
    run_cmd.add_argument("--ref", default="", help="Optional git ref")
    run_cmd.add_argument(
        "--mode",
        choices=[mode.value for mode in Mode],
        default="",
        help="Optional mode override (manual|semi|auto)",
    )
    run_cmd.add_argument(
        "--heal-orphans",
        action="store_true",
        help="Allow healing orphaned processed queue items during stage 2b",
    )
    run_cmd.add_argument(
        "--max-steps",
        type=int,
        default=25,
        help="Maximum steps per iteration for semi/auto mode safety",
    )
    run_cmd.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximum iterations in auto mode safety loop",
    )
    return parser


def _status_for_repo(*, repo: str, ref: str) -> dict[str, Any]:
    server_settings = ServerSettings()
    return _loop_status_for_repo(
        settings=server_settings,
        active_repo=repo,
        ref=ref,
    )


def _stage(status: dict[str, Any]) -> str:
    raw = status.get("stage")
    if isinstance(raw, str):
        return raw
    return ""


def _stage_reason(status: dict[str, Any]) -> str:
    raw = status.get("stageReason")
    if isinstance(raw, str):
        return raw
    return ""


def _work_remaining(status: dict[str, Any]) -> bool:
    stage = _stage(status)
    if not stage:
        return False
    return True


def _resolve_repo(explicit_repo: str) -> str:
    if explicit_repo:
        return explicit_repo
    server_settings = ServerSettings()
    return server_settings.default_repo


def _log_result_details(result: dict[str, Any] | None) -> None:
    if not isinstance(result, dict):
        return

    issue_number = result.get("issueNumber")
    if isinstance(issue_number, int):
        _log(f"Created issue #{issue_number}")

    pull_number = result.get("pullNumber")
    if isinstance(pull_number, int):
        _log(f"Created PR #{pull_number}")

    merged_pr = result.get("mergedPullNumber")
    if isinstance(merged_pr, int):
        _log(f"Merged PR #{merged_pr}")


def run_single_step(*, repo: str, ref: str, heal_orphans: bool, mode: Mode) -> int:
    """Run exactly one deterministic loop transition."""

    auto_approve = should_auto_approve(mode)
    exit_code, result, message = run_once(
        repo=repo,
        ref=ref,
        heal_orphans=heal_orphans,
        auto_approve=auto_approve,
    )
    if message:
        _log(message)
    _log_result_details(result)
    return exit_code


def run_single_iteration(
    *,
    repo: str,
    ref: str,
    heal_orphans: bool,
    mode: Mode,
    max_steps: int,
    iteration_number: int,
) -> int:
    """Run one full iteration until completion or a safe blocking point."""

    _log(f"Starting iteration {iteration_number}")

    for _ in range(max_steps):
        status_before = _status_for_repo(repo=repo, ref=ref)
        stage_before = _stage(status_before)

        if not _work_remaining(status_before):
            _log("Stopping (no remaining work detected)")
            return 0

        if stage_before in MERGE_STAGES and not should_auto_approve(mode):
            _log("Waiting for approval...")
            _log(f"Stopping ({mode.value} mode complete)")
            return 0

        exit_code = run_single_step(repo=repo, ref=ref, heal_orphans=heal_orphans, mode=mode)
        if exit_code != 0:
            return exit_code

        status_after = _status_for_repo(repo=repo, ref=ref)
        stage_after = _stage(status_after)

        if not _work_remaining(status_after):
            _log("Stopping (iteration complete)")
            return 0

        if stage_after == stage_before:
            if stage_after in {"1b", "2b", "3b"}:
                _log("Waiting for PR completion...")
            _log(f"Stopping ({mode.value} mode complete)")
            return 0

    _log(f"Stopping ({mode.value} mode max steps reached)")
    return 0


def run_auto_loop(
    *,
    repo: str,
    ref: str,
    heal_orphans: bool,
    max_steps: int,
    max_iterations: int,
) -> int:
    """Run continuous automatic iterations until stop condition is reached."""

    for iteration in range(1, max_iterations + 1):
        status = _status_for_repo(repo=repo, ref=ref)
        if not _work_remaining(status):
            _log("Stopping (auto mode complete: no remaining work)")
            return 0

        exit_code = run_single_iteration(
            repo=repo,
            ref=ref,
            heal_orphans=heal_orphans,
            mode=Mode.AUTO,
            max_steps=max_steps,
            iteration_number=iteration,
        )
        if exit_code != 0:
            return exit_code

    _log("Stopping (auto mode stop condition: max iterations reached)")
    return 0


def _resolve_mode(*, override_mode: str, repo_root: Path) -> Mode:
    config = load_runtime_config(repo_root)
    if override_mode:
        return Mode(override_mode)
    return config.mode


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for ``gao`` CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help(sys.stderr)
        return 2

    repo_root = Path.cwd()
    mode = _resolve_mode(override_mode=args.mode, repo_root=repo_root)
    _log(f"Repo root: {repo_root}")
    _log(f"Mode: {mode.value}")

    repo = _resolve_repo(args.repo)
    if not repo:
        _log("Missing repo. Pass --repo or set ORCHESTRATOR_DEFAULT_REPO.")
        return 2

    if mode == Mode.MANUAL:
        return run_single_step(repo=repo, ref=args.ref, heal_orphans=args.heal_orphans, mode=mode)

    if mode == Mode.SEMI:
        return run_single_iteration(
            repo=repo,
            ref=args.ref,
            heal_orphans=args.heal_orphans,
            mode=mode,
            max_steps=args.max_steps,
            iteration_number=1,
        )

    return run_auto_loop(
        repo=repo,
        ref=args.ref,
        heal_orphans=args.heal_orphans,
        max_steps=args.max_steps,
        max_iterations=args.max_iterations,
    )


if __name__ == "__main__":
    raise SystemExit(main())
