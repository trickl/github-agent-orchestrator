"""Inspect (and optionally perform) review archiving in a target repo.

This script is intended for debugging review-mode termination.

It will:
- List active review sources under planning/reviews (excluding completed/ and *.actions.md)
- For the first active review, evaluate whether the orchestrator would archive it
  (based on the most recent closed review-consumption issue + evidence of queue output)
- Optionally perform the archive move into planning/reviews/completed/

Safety:
- No writes are performed unless ORCHESTRATOR_CONFIRM_ARCHIVE=1.

Usage:
    python scripts/inspect_review_archiving.py owner/repo

Env:
- ORCHESTRATOR_GITHUB_TOKEN (required)
- ORCHESTRATOR_CONFIRM_ARCHIVE=1 (optional; enables writes)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from github_agent_orchestrator.server import dashboard_router
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard import github_operations


def _require_repo_arg(argv: list[str]) -> str:
    if len(argv) < 2 or not argv[1].strip():
        raise SystemExit("Usage: python scripts/inspect_review_archiving.py owner/repo")
    return argv[1].strip()


def _active_review_sources(*, settings: ServerSettings, repo: str, branch: str) -> list[str]:
    paths = github_operations.list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/reviews",
        ref=branch,
    )

    out: list[str] = []
    for p in paths:
        norm = str(p).replace("\\", "/")
        if "/completed/" in norm:
            continue
        name = Path(norm).name.lower()
        if not name.startswith("review-"):
            continue
        if name.endswith(".actions.md"):
            continue
        out.append(norm)
    return sorted(out)


def _queue_review_candidates(*, settings: ServerSettings, repo: str, branch: str) -> list[str]:
    out: list[str] = []
    for d in (
        "planning/issue_queue/pending",
        "planning/issue_queue/processed",
        "planning/issue_queue/complete",
    ):
        try:
            paths = github_operations.list_repo_markdown_files_under(
                settings=settings,
                repository=repo,
                dir_path=d,
                ref=branch,
            )
        except Exception:
            continue
        for p in paths:
            norm = str(p).replace("\\", "/")
            if Path(norm).name.lower().startswith("review-"):
                out.append(norm)
    return sorted(set(out))


def main() -> int:
    repo = _require_repo_arg(sys.argv)

    # Ensure the settings reflect current env, but do not require default repo.
    settings = ServerSettings()
    if not settings.github_token.strip():
        raise SystemExit("ORCHESTRATOR_GITHUB_TOKEN is required")

    branch = github_operations.get_default_branch(settings=settings, repository=repo)

    sources = _active_review_sources(settings=settings, repo=repo, branch=branch)
    print(f"repo: {repo}")
    print(f"branch: {branch}")
    print(f"active review sources: {len(sources)}")
    for p in sources[:20]:
        print(f"  - {p}")
    if len(sources) > 20:
        print(f"  (+{len(sources) - 20} more)")

    queue_review = _queue_review_candidates(settings=settings, repo=repo, branch=branch)
    print(f"review queue artefacts (any state): {len(queue_review)}")
    for p in queue_review[:20]:
        print(f"  - {p}")
    if len(queue_review) > 20:
        print(f"  (+{len(queue_review) - 20} more)")

    if not sources:
        print("No active review sources found under planning/reviews.")
        return 0

    review_path = sources[0]
    print("\n--- evaluate first active review ---")
    print(f"review_path: {review_path}")

    marker_prefix = getattr(dashboard_router, "_REVIEW_CONSUMPTION_MARKER_PREFIX", "orchestrator:review-consumption")
    marker = f"{marker_prefix} {review_path}"
    try:
        closed_issue_num = github_operations.search_issue_number_by_body_marker(
            settings=settings,
            repository=repo,
            marker=marker,
            state="closed",
        )
    except Exception:
        closed_issue_num = None

    print(f"most_recent_closed_review_consumption_issue: {closed_issue_num}")

    if isinstance(closed_issue_num, int):
        try:
            issue = dashboard_router._github_get_json(
                settings,
                url=dashboard_router._repo_api_url(
                    settings,
                    repository=repo,
                    path=f"issues/{closed_issue_num}",
                ),
            )
        except Exception:
            issue = None

        if isinstance(issue, dict):
            created_at = issue.get("created_at")
            closed_at = issue.get("closed_at")
            created_dt = (
                dashboard_router._dt_from_iso(created_at)
                if isinstance(created_at, str)
                else None
            )
            closed_dt = (
                dashboard_router._dt_from_iso(closed_at)
                if isinstance(closed_at, str)
                else None
            )
            created_epoch = int(created_dt.timestamp()) if created_dt is not None else None
            closed_epoch = int(closed_dt.timestamp()) if closed_dt is not None else None

            try:
                produced = dashboard_router._review_consumption_issue_produced_queue_output(
                    settings=settings,
                    repo=repo,
                    branch=branch,
                    review_path=review_path,
                    issue_created_epoch=created_epoch,
                    issue_closed_epoch=closed_epoch,
                )
            except Exception:
                produced = None

            print(
                "output_evidence_detected:",
                produced,
                f"(created_epoch={created_epoch}, closed_epoch={closed_epoch})",
            )

    try:
        should_archive = dashboard_router._review_consumption_candidate_should_be_archived(
            settings=settings,
            repo=repo,
            branch=branch,
            review_path=review_path,
        )
    except Exception as e:
        print("ERROR evaluating candidate:")
        print(repr(e))
        return 2

    print(f"would_archive: {should_archive}")

    confirm = os.environ.get("ORCHESTRATOR_CONFIRM_ARCHIVE", "").strip() == "1"
    print(f"confirm_archive: {confirm}")

    if not should_archive:
        print("Not attempting archive (candidate does not meet archive criteria).")
        return 0

    if not confirm:
        print("Dry-run only. Set ORCHESTRATOR_CONFIRM_ARCHIVE=1 to perform archive writes.")
        return 0

    print("\n--- performing archive ---")
    try:
        dashboard_router._archive_review_and_actions_if_present(
            settings=settings,
            repo=repo,
            branch=branch,
            review_path=review_path,
        )
    except Exception as e:
        print("ARCHIVE FAILED:")
        # FastAPI HTTPException has .status_code and .detail
        status = getattr(e, "status_code", None)
        detail = getattr(e, "detail", None)
        print(json.dumps({"type": type(e).__name__, "status_code": status, "detail": detail}, indent=2))
        print(repr(e))
        return 3

    print("Archive succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
