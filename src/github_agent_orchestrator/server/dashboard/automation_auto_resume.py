"""Auto-resume automation for nudging Copilot after rate limit failures.

This module contains the logic for automatically posting resume comments to PRs
after detecting Copilot SWE Agent failures, helping to recover from rate limit
issues without manual intervention.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings


def maybe_auto_resume_copilot_after_rate_limit(
    *,
    settings: ServerSettings,
    repository: str,
    pr_number: int,
) -> str | None:
    """If enabled, post a resume nudge comment after detecting Copilot SWE Agent failure.

    In practice, Copilot SWE Agent "stop" signals are most reliably observed via
    the REST issue events stream (e.g. `copilot_work_finished_failure`).

    The mechanism is intentionally simple and idempotent:
    - Detect the latest `copilot_work_finished_failure` for the PR.
    - Wait N minutes (default 45) after that timestamp.
    - Post a single resume nudge comment tagging @copilot.
    - Do not post if Copilot has started again after the failure.
    - Do not post if we've already posted a nudge after that failure.
    - Enforce a small "nudge budget" to avoid infinite retries.
    """
    # Import here to avoid circular dependency at module load time
    from github_agent_orchestrator.server import dashboard_router

    if not settings.auto_resume_copilot_on_rate_limit:
        return None
    if not settings.github_token.strip():
        return None

    delay_minutes = int(settings.auto_resume_copilot_on_rate_limit_delay_minutes)
    max_nudges = int(getattr(settings, "auto_resume_copilot_max_nudges", 3))
    window_minutes = int(getattr(settings, "auto_resume_copilot_nudge_window_minutes", 1440))

    now = dashboard_router._utc_now()

    try:
        events = dashboard_router._list_issue_events_raw(
            settings, repository=repository, issue_number=pr_number
        )
    except HTTPException:
        # Best-effort only: do not break status rendering.
        return None

    latest_failure_iso: str | None = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("event") != "copilot_work_finished_failure":
            continue
        created_at = ev.get("created_at")
        if not isinstance(created_at, str) or not created_at.strip():
            continue

        # Best-effort: ensure the event was produced via the Copilot SWE Agent app.
        app = ev.get("performed_via_github_app")
        slug = app.get("slug") if isinstance(app, dict) else None
        if isinstance(slug, str) and slug.strip() and slug.strip().lower() != "copilot-swe-agent":
            continue

        if latest_failure_iso is None or created_at > latest_failure_iso:
            latest_failure_iso = created_at

    if latest_failure_iso is None:
        return None

    # If Copilot has started work again after the failure, don't nudge.
    for ev in events:
        if not isinstance(ev, dict):
            continue
        created_at = ev.get("created_at")
        if not isinstance(created_at, str) or created_at <= latest_failure_iso:
            continue
        if ev.get("event") in {"copilot_work_started", "copilot_work_finished_success"}:
            return None

    failure_dt = dashboard_router._dt_from_iso(latest_failure_iso)
    due_dt = failure_dt + timedelta(minutes=delay_minutes)
    if now < due_dt:
        remaining = int(max(0, (due_dt - now).total_seconds()) // 60)
        return (
            f"Copilot failure detected on PR #{pr_number} at {latest_failure_iso}; "
            f"auto-resume eligible in ~{remaining} minutes."
        )

    try:
        comments = dashboard_router._list_issue_comments_raw(
            settings, repository=repository, issue_number=pr_number
        )
    except HTTPException:
        # If we can't check for idempotency/budget, don't risk spamming.
        return None

    # Do not post if a resume nudge already exists after the failure timestamp.
    for it in comments:
        if not isinstance(it, dict):
            continue
        created_at = it.get("created_at")
        if not isinstance(created_at, str) or created_at <= latest_failure_iso:
            continue
        body = it.get("body")
        if isinstance(body, str) and dashboard_router._comment_body_is_copilot_resume_nudge(body):
            return None

    # Enforce a simple "nudge budget" to prevent infinite retry loops.
    # Budget window is the max of: (now - window_minutes) and the last observed Copilot start/success.
    last_progress_iso: str | None = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("event") not in {"copilot_work_started", "copilot_work_finished_success"}:
            continue
        created_at = ev.get("created_at")
        if not isinstance(created_at, str) or not created_at.strip():
            continue
        if created_at > latest_failure_iso:
            continue
        if last_progress_iso is None or created_at > last_progress_iso:
            last_progress_iso = created_at

    cutoff_dt = now - timedelta(minutes=window_minutes)
    if last_progress_iso is not None:
        cutoff_dt = max(cutoff_dt, dashboard_router._dt_from_iso(last_progress_iso))

    nudge_count = 0
    for it in comments:
        if not isinstance(it, dict):
            continue
        created_at = it.get("created_at")
        if not isinstance(created_at, str) or not created_at.strip():
            continue
        if dashboard_router._dt_from_iso(created_at) < cutoff_dt:
            continue
        body = it.get("body")
        if isinstance(body, str) and dashboard_router._comment_body_is_copilot_resume_nudge(body):
            nudge_count += 1

    if max_nudges <= 0:
        return "Auto-resume suppressed (nudge budget disabled)."
    if nudge_count >= max_nudges:
        return (
            "Auto-resume suppressed (nudge budget exhausted): "
            f"{nudge_count}/{max_nudges} resume nudges within the active window."
        )

    dashboard_router._github_post_json(
        settings,
        url=dashboard_router._repo_api_url(
            settings, repository=repository, path=f"issues/{pr_number}/comments"
        ),
        payload={"body": dashboard_router._COPILOT_RATE_LIMIT_RESUME_COMMENT},
    )
    return f"Posted auto-resume comment on PR #{pr_number} after Copilot failure."


def _copilot_login_candidates(settings: ServerSettings) -> set[str]:
    """Return likely GitHub logins for the Copilot SWE Agent account."""

    raw = settings.copilot_assignee.strip()
    out: set[str] = {"copilot-swe-agent"}
    if raw:
        cleaned = raw.strip().lstrip("@").strip().lower()
        if cleaned:
            out.add(cleaned)
            out.add(cleaned.replace("[bot]", "").strip())
    return {c for c in out if c}
