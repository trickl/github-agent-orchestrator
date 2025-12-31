"""Dashboard-focused REST API.

This router implements the endpoints used by the React dashboard in `ui/`.

All routes are mounted under `/api`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueStore
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard_store import (
    GenerationRuleModel,
    NotFound,
    RuleStore,
    TimelineEventModel,
    TimelineStore,
    read_markdown_doc,
    write_issue_queue_item,
)

router = APIRouter()


def _settings(request: Request) -> ServerSettings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, ServerSettings):
        # This should never happen for the real app, but keeps the API fail-fast.
        raise HTTPException(status_code=500, detail="Server settings not configured")
    return settings


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _dt_from_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=UTC)


def _issue_status(record_status: str, pr_completion: str | None) -> str:
    s = (record_status or "").strip().lower()
    if pr_completion == "merged":
        return "MERGED"
    if pr_completion == "closed":
        return "CLOSED"
    if pr_completion == "timeout":
        return "FAILED"
    if s in {"closed", "done"}:
        return "CLOSED"
    if s in {"open", "opened"}:
        return "OPEN"
    return "UNKNOWN"


def _issue_type_path(source_queue_path: str | None) -> str:
    # UI expects a human-ish folder label.
    # We'll map by convention when possible.
    p = (source_queue_path or "").strip()
    if not p:
        return "unknown"
    # Example: planning/issue_queue/pending/dev-20250101.md
    if "planning/issue_queue/pending" in p:
        return "planning/issue_queue/pending"
    return p


def _make_github_issue_url(repo: str, issue_number: int) -> str | None:
    if not repo.strip():
        return None
    return f"https://github.com/{repo.strip()}/issues/{issue_number}"


def _template_category_from_filename(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("review-"):
        return "review"
    if lowered.startswith("gap-"):
        return "gap"
    if lowered.startswith("system-"):
        return "system"
    if lowered.startswith("maintenance-"):
        return "maintenance"
    return "unknown"


def _load_template_rules(templates_dir: Path) -> list[GenerationRuleModel]:
    if not templates_dir.exists():
        return []

    rules: list[GenerationRuleModel] = []
    for path in sorted(templates_dir.glob("*.md")):
        content, _ts = read_markdown_doc(path)
        rules.append(
            GenerationRuleModel(
                id=path.name,
                name=path.stem.replace("_", " "),
                category=_template_category_from_filename(path.stem),
                enabled=True,
                promptText=content,
                targetFolder="planning/issue_queue/pending",
                trigger={"kind": "MANUAL_ONLY"},
                editable=False,
            )
        )
    return rules


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/docs/goal")
def doc_goal(request: Request) -> dict[str, object]:
    path = _settings(request).planning_root / "vision" / "goal.md"
    content, ts = read_markdown_doc(path)
    return {
        "key": "goal",
        "title": "Goal",
        "path": str(path),
        "lastUpdatedIso": ts,
        "content": content,
    }


@router.get("/docs/capabilities")
def doc_capabilities(request: Request) -> dict[str, object]:
    path = _settings(request).planning_root / "state" / "system_capabilities.md"
    content, ts = read_markdown_doc(path)
    return {
        "key": "capabilities",
        "title": "System Capabilities",
        "path": str(path),
        "lastUpdatedIso": ts,
        "content": content,
    }


@router.get("/rules")
def list_rules(request: Request) -> list[dict[str, object]]:
    settings = _settings(request)
    store = RuleStore(settings.rules_state_file)

    # Built-in rules from planning/issue_templates (read-only)
    template_rules = _load_template_rules(settings.planning_root / "issue_templates")
    json_rules = store.list()

    # Prefer JSON rules when IDs collide (allows override/migration later).
    by_id: dict[str, GenerationRuleModel] = {r.id: r for r in template_rules}
    for r in json_rules:
        by_id[r.id] = r

    merged = list(by_id.values())
    merged.sort(key=lambda r: r.name.lower())
    return [r.model_dump(mode="json") for r in merged]


@router.post("/rules")
def create_rule(request: Request, payload: dict[str, object]) -> dict[str, object]:
    store = RuleStore(_settings(request).rules_state_file)
    created = store.create(payload)
    return created.model_dump(mode="json")


@router.put("/rules/{rule_id}")
def update_rule(request: Request, rule_id: str, payload: dict[str, object]) -> dict[str, object]:
    store = RuleStore(_settings(request).rules_state_file)
    # Reject edits to template-backed rules.
    if rule_id.endswith(".md"):
        raise HTTPException(status_code=409, detail="Template rules are read-only for now")
    # Ensure path param wins.
    rule = GenerationRuleModel.model_validate({"id": rule_id, **payload})
    updated = store.upsert(rule)
    return updated.model_dump(mode="json")


@router.delete("/rules/{rule_id}")
def delete_rule(request: Request, rule_id: str) -> dict[str, object]:
    store = RuleStore(_settings(request).rules_state_file)
    if rule_id.endswith(".md"):
        raise HTTPException(status_code=409, detail="Template rules are read-only for now")
    store.delete(rule_id)
    return {"ok": True}


@router.post("/rules/{rule_id}/run")
def run_rule(request: Request, rule_id: str) -> dict[str, object]:
    # For now, "run" means: create a pending issue-queue artefact and record a timeline event.
    # This uses the existing orchestrator flow (issue queue -> promotion) without requiring
    # GitHub credentials.
    settings = _settings(request)
    rule_store = RuleStore(settings.rules_state_file)
    timeline_store = TimelineStore(settings.timeline_state_file)

    # Resolve rule from either templates or JSON store.
    template_rules = _load_template_rules(settings.planning_root / "issue_templates")
    template_map = {r.id: r for r in template_rules}
    if rule_id in template_map:
        rule = template_map[rule_id]
    else:
        try:
            rule = rule_store.get(rule_id)
        except NotFound as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    if not rule.enabled:
        raise HTTPException(status_code=409, detail="Rule is disabled")

    pending_dir = settings.planning_root / "issue_queue" / "pending"
    # Align with repo convention: dev-<timestamp>.md
    artefact_path = write_issue_queue_item(
        pending_dir,
        prefix="dev",
        title=rule.name,
        body=rule.promptText,
    )

    event_id = f"evt_{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S%f')}"
    timeline_store.append(
        TimelineEventModel(
            id=event_id,
            tsIso=_utc_now_iso(),
            kind="ISSUE_FILE_CREATED",
            summary=f"Created issue-queue artefact for rule: {rule.name}",
            ruleId=rule.id,
            issueId=str(artefact_path.name),
            issueTitle=rule.name,
            typePath=rule.targetFolder or "planning/issue_queue/pending",
            links=[{"label": "Artefact", "url": str(artefact_path)}],
        )
    )

    rule_store.touch_last_run(rule.id)

    return {
        "ok": True,
        "createdIssueId": artefact_path.name,
        "createdIssueTitle": rule.name,
        "timelineEventId": event_id,
    }


@router.get("/timeline")
def list_timeline(
    request: Request, limit: int = Query(default=200, ge=1, le=1000)
) -> list[dict[str, object]]:
    settings = _settings(request)
    store = TimelineStore(settings.timeline_state_file)
    events = store.list()

    # If no explicit timeline exists yet, derive a minimal one from issue state.
    if not events:
        issue_store = IssueStore(settings.issues_state_file)
        for r in issue_store.load():
            repo = r.repository.strip() or settings.default_repo.strip()
            issue_url = _make_github_issue_url(repo, r.issue_number)
            events.append(
                TimelineEventModel(
                    id=f"issue_{r.issue_number}",
                    tsIso=r.created_at,
                    kind="GITHUB_ISSUE_OPENED",
                    summary=f"Created issue: {r.title}",
                    issueId=str(r.issue_number),
                    issueTitle=r.title,
                    typePath=_issue_type_path(r.source_queue_path),
                    links=([{"label": "GitHub Issue", "url": issue_url}] if issue_url else None),
                )
            )

    events.sort(key=lambda e: e.tsIso, reverse=True)
    return [e.model_dump(mode="json") for e in events[:limit]]


@router.get("/issues")
def list_issues(request: Request, status: str = Query(default="open")) -> list[dict[str, object]]:
    # Backed by existing IssueStore persisted JSON.
    settings = _settings(request)
    issue_store = IssueStore(settings.issues_state_file)
    records = issue_store.load()

    # Determine repo context and filter.
    repo_param = request.query_params.get("repo", "").strip()
    active_repo = repo_param or settings.default_repo.strip()

    # Determine an "active" issue: prefer a running job if present, otherwise newest open.
    active_issue_number: int | None = None
    jobs_path = settings.jobs_state_file
    if jobs_path.exists():
        try:
            raw = jobs_path.read_text(encoding="utf-8")
            # JobStore uses JSON list; but don't import it here to keep router lightweight.
            import json

            jobs = json.loads(raw)
            if isinstance(jobs, list):
                running = [j for j in jobs if isinstance(j, dict) and j.get("status") == "running"]
                if running:
                    raw_issue_number = running[0].get("issue_number")
                    if isinstance(raw_issue_number, int):
                        active_issue_number = raw_issue_number
                    elif isinstance(raw_issue_number, str):
                        try:
                            active_issue_number = int(raw_issue_number)
                        except ValueError:
                            active_issue_number = None
        except Exception:
            active_issue_number = None

    mapped: list[dict[str, object]] = []
    now = datetime.now(tz=UTC)

    for r in records:
        record_repo = (r.repository or "").strip() or active_repo

        if active_repo and record_repo.strip() != active_repo:
            continue

        st = _issue_status(r.status, r.pr_completion)
        if status == "open" and st in {"CLOSED", "MERGED"}:
            continue

        created_dt = _dt_from_iso(r.created_at)
        last_updated_iso = r.pr_last_checked_at or r.created_at
        age_seconds = max(0, int((now - created_dt).total_seconds()))

        pr_url: str | None = None
        if r.linked_pull_requests:
            first = r.linked_pull_requests[0]
            if isinstance(first, dict):
                pr_url = str(first.get("html_url") or first.get("url") or "").strip() or None

        mapped.append(
            {
                "id": str(r.issue_number),
                "title": r.title,
                "typePath": _issue_type_path(r.source_queue_path),
                "status": st,
                "ageSeconds": age_seconds,
                "githubIssueUrl": _make_github_issue_url(record_repo, r.issue_number),
                "prUrl": pr_url,
                "lastUpdatedIso": last_updated_iso,
                "isActive": (active_issue_number == r.issue_number),
            }
        )

    # If no running job, pick newest open issue as active (for UI highlighting).
    if active_issue_number is None:
        open_issues = [i for i in mapped if i.get("status") not in {"CLOSED", "MERGED"}]
        if open_issues:
            newest = max(open_issues, key=lambda i: str(i.get("lastUpdatedIso") or ""))
            for i in mapped:
                i["isActive"] = i["id"] == newest.get("id")

    mapped.sort(key=lambda i: str(i.get("lastUpdatedIso") or ""), reverse=True)
    return mapped


@router.get("/active")
def get_active(request: Request) -> dict[str, object]:
    issues = list_issues(request, status="open")
    active = next((i for i in issues if i.get("isActive") is True), None)

    timeline = TimelineStore(_settings(request).timeline_state_file)
    last = timeline.latest()

    return {
        "activeIssue": active,
        "lastAction": (
            None
            if last is None
            else {
                "tsIso": last.tsIso,
                "summary": last.summary,
            }
        ),
    }


@router.post("/issues/refresh")
def refresh_issues_from_github(request: Request) -> dict[str, int]:
    """Refresh issue open/closed status from GitHub.

    This reconciles local state with GitHub so the dashboard can display correct
    statuses and counts.
    """

    settings = _settings(request)
    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required for this endpoint",
        )

    repo_param = request.query_params.get("repo", "").strip()
    active_repo = repo_param or settings.default_repo.strip()

    store = IssueStore(settings.issues_state_file)
    records = store.load()

    clients: dict[str, GitHubClient] = {}
    updated = 0

    def get_client(repo: str) -> GitHubClient:
        if repo not in clients:
            clients[repo] = GitHubClient(
                token=settings.github_token,
                repository=repo,
                base_url=settings.github_base_url,
            )
        return clients[repo]

    try:
        for r in records:
            record_repo = (r.repository or "").strip() or active_repo
            if not record_repo:
                # No repo context available; cannot refresh.
                continue

            if active_repo and record_repo != active_repo:
                continue

            details = get_client(record_repo).get_issue(issue_number=r.issue_number)
            store.upsert(
                r.model_copy(
                    update={
                        "repository": record_repo,
                        "status": details.status,
                        "assignees": details.assignees,
                    }
                )
            )
            updated += 1
    finally:
        for c in clients.values():
            c.close()

    return {"updated": updated}


@router.get("/overview")
def overview(request: Request) -> dict[str, object]:
    issues = list_issues(request, status="open")
    open_count = len([i for i in issues if i.get("status") not in {"CLOSED", "MERGED"}])
    active = next((i for i in issues if i.get("isActive") is True), None)

    timeline = TimelineStore(_settings(request).timeline_state_file)
    last = timeline.latest()

    return {
        "activeIssueId": None if active is None else active.get("id"),
        "openIssueCount": open_count,
        "lastEventIso": (last.tsIso if last is not None else _utc_now_iso()),
    }
