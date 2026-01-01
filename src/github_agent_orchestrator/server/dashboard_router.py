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
    CognitiveTaskModel,
    CognitiveTaskStore,
    NotFound,
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


def _count_markdown_files(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return len([p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".md"])


def _load_running_job(settings: ServerSettings) -> dict[str, object] | None:
    """Return a lightweight summary of the first running job, if any."""

    jobs_path = settings.jobs_state_file
    if not jobs_path.exists():
        return None

    try:
        import json

        raw = jobs_path.read_text(encoding="utf-8")
        jobs = json.loads(raw)
        if not isinstance(jobs, list):
            return None

        running = [j for j in jobs if isinstance(j, dict) and j.get("status") == "running"]
        if not running:
            return None

        job = running[0]
        issue_number: int | None

        raw_issue_number = job.get("issue_number")
        if isinstance(raw_issue_number, int):
            issue_number = raw_issue_number
        elif isinstance(raw_issue_number, str):
            try:
                issue_number = int(raw_issue_number)
            except ValueError:
                issue_number = None
        else:
            issue_number = None

        return {
            "jobId": str(job.get("job_id") or ""),
            "issueNumber": issue_number,
            "status": "running",
            "updatedAt": str(job.get("updated_at") or ""),
        }
    except Exception:
        return None


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


def _load_template_cognitive_tasks(templates_dir: Path) -> list[CognitiveTaskModel]:
    if not templates_dir.exists():
        return []

    tasks: list[CognitiveTaskModel] = []
    for path in sorted(templates_dir.glob("*.md")):
        content, _ts = read_markdown_doc(path)
        tasks.append(
            CognitiveTaskModel(
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
    return tasks


def _ensure_cognitive_tasks_state_file(settings: ServerSettings) -> Path:
    """Return the canonical cognitive tasks state file, migrating legacy state if needed."""

    new_path = settings.cognitive_tasks_state_file
    legacy_path = settings.legacy_generation_rules_state_file

    if new_path.exists():
        return new_path
    if legacy_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
        return new_path
    return new_path


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


@router.get("/cognitive-tasks")
@router.get("/rules", deprecated=True)
def list_cognitive_tasks(request: Request) -> list[dict[str, object]]:
    settings = _settings(request)
    store = CognitiveTaskStore(_ensure_cognitive_tasks_state_file(settings))

    # Built-in cognitive tasks from planning/issue_templates (read-only)
    template_tasks = _load_template_cognitive_tasks(settings.planning_root / "issue_templates")
    json_tasks = store.list()

    # Prefer JSON tasks when IDs collide (allows override/migration later).
    by_id: dict[str, CognitiveTaskModel] = {t.id: t for t in template_tasks}
    for t in json_tasks:
        by_id[t.id] = t

    merged = list(by_id.values())
    merged.sort(key=lambda t: t.name.lower())
    return [r.model_dump(mode="json") for r in merged]


@router.post("/cognitive-tasks")
@router.post("/rules", deprecated=True)
def create_cognitive_task(request: Request, payload: dict[str, object]) -> dict[str, object]:
    settings = _settings(request)
    store = CognitiveTaskStore(_ensure_cognitive_tasks_state_file(settings))
    created = store.create(payload)
    return created.model_dump(mode="json")


@router.put("/cognitive-tasks/{task_id}")
@router.put("/rules/{task_id}", deprecated=True)
def update_cognitive_task(
    request: Request, task_id: str, payload: dict[str, object]
) -> dict[str, object]:
    settings = _settings(request)
    store = CognitiveTaskStore(_ensure_cognitive_tasks_state_file(settings))
    # Reject edits to template-backed cognitive tasks.
    if task_id.endswith(".md"):
        raise HTTPException(
            status_code=409, detail="Template cognitive tasks are read-only for now"
        )
    # Ensure path param wins.
    task = CognitiveTaskModel.model_validate({"id": task_id, **payload})
    updated = store.upsert(task)
    return updated.model_dump(mode="json")


@router.delete("/cognitive-tasks/{task_id}")
@router.delete("/rules/{task_id}", deprecated=True)
def delete_cognitive_task(request: Request, task_id: str) -> dict[str, object]:
    settings = _settings(request)
    store = CognitiveTaskStore(_ensure_cognitive_tasks_state_file(settings))
    if task_id.endswith(".md"):
        raise HTTPException(
            status_code=409, detail="Template cognitive tasks are read-only for now"
        )
    store.delete(task_id)
    return {"ok": True}


@router.post("/cognitive-tasks/{task_id}/run")
@router.post("/rules/{task_id}/run", deprecated=True)
def run_cognitive_task(request: Request, task_id: str) -> dict[str, object]:
    # For now, "run" means: create a pending issue-queue artefact and record a timeline event.
    # This uses the existing orchestrator flow (issue queue -> promotion) without requiring
    # GitHub credentials.
    settings = _settings(request)
    task_store = CognitiveTaskStore(_ensure_cognitive_tasks_state_file(settings))
    timeline_store = TimelineStore(settings.timeline_state_file)

    # Resolve cognitive task from either templates or JSON store.
    template_tasks = _load_template_cognitive_tasks(settings.planning_root / "issue_templates")
    template_map = {t.id: t for t in template_tasks}
    if task_id in template_map:
        task = template_map[task_id]
    else:
        try:
            task = task_store.get(task_id)
        except NotFound as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    if not task.enabled:
        raise HTTPException(status_code=409, detail="Cognitive task is disabled")

    pending_dir = settings.planning_root / "issue_queue" / "pending"
    # Align with repo convention: dev-<timestamp>.md
    artefact_path = write_issue_queue_item(
        pending_dir,
        prefix="dev",
        title=task.name,
        body=task.promptText,
    )

    event_id = f"evt_{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S%f')}"
    timeline_store.append(
        TimelineEventModel(
            id=event_id,
            tsIso=_utc_now_iso(),
            kind="ISSUE_FILE_CREATED",
            summary=f"Created issue-queue artefact for cognitive task: {task.name}",
            cognitiveTaskId=task.id,
            issueId=str(artefact_path.name),
            issueTitle=task.name,
            typePath=task.targetFolder or "planning/issue_queue/pending",
            links=[{"label": "Artefact", "url": str(artefact_path)}],
        )
    )

    task_store.touch_last_run(task.id)

    return {
        "ok": True,
        "createdIssueId": artefact_path.name,
        "createdIssueTitle": task.name,
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


@router.get("/loop")
def loop_status(request: Request) -> dict[str, object]:
    """Return a UI-friendly summary of the orchestrator's A–G loop.

    The intent is to help visualize where the system currently is *without* adding
    new "intelligence". This is a best-effort stage derived from persisted state.
    """

    settings = _settings(request)

    pending_dir = settings.planning_root / "issue_queue" / "pending"
    processed_dir = settings.planning_root / "issue_queue" / "processed"
    complete_dir = settings.planning_root / "issue_queue" / "complete"

    pending_count = _count_markdown_files(pending_dir)
    processed_count = _count_markdown_files(processed_dir)
    complete_count = _count_markdown_files(complete_dir)

    issue_store = IssueStore(settings.issues_state_file)
    records = issue_store.load()

    def is_open(record_status: str, pr_completion: str | None) -> bool:
        return _issue_status(record_status, pr_completion) not in {"CLOSED", "MERGED"}

    open_records = [r for r in records if is_open(r.status, r.pr_completion)]

    caps_update_prefix = "Update system capabilities based on merged PR"
    open_caps_updates = [r for r in open_records if (r.title or "").startswith(caps_update_prefix)]

    # Unpromoted pending files are queue artefacts not yet associated with an IssueRecord.
    promoted_paths = {
        str((r.source_queue_path or "").strip()) for r in records if r.source_queue_path
    }
    unpromoted_pending = 0
    if pending_dir.exists() and pending_dir.is_dir():
        for p in pending_dir.iterdir():
            if not (p.is_file() and p.suffix.lower() == ".md"):
                continue
            queue_path = f"planning/issue_queue/pending/{p.name}"
            if queue_path not in promoted_paths:
                unpromoted_pending += 1

    running_job = _load_running_job(settings)

    if running_job is not None:
        stage = "D"
        stage_label = "PR completion & merge"
        active_step = 3
    elif open_caps_updates:
        stage = "F"
        stage_label = "Capability update execution"
        active_step = 5
    elif open_records:
        stage = "C"
        stage_label = "Development (Copilot)"
        active_step = 2
    elif unpromoted_pending > 0:
        stage = "B"
        stage_label = "Issue creation"
        active_step = 1
    else:
        stage = "A"
        stage_label = "Gap analysis"
        active_step = 0

    timeline = TimelineStore(settings.timeline_state_file)
    last = timeline.latest()

    return {
        "nowIso": _utc_now_iso(),
        "stage": stage,
        "stageLabel": stage_label,
        "activeStep": active_step,
        "counts": {
            "pending": pending_count,
            "processed": processed_count,
            "complete": complete_count,
            "openIssues": len(open_records),
            "openCapabilityUpdateIssues": len(open_caps_updates),
            "unpromotedPending": unpromoted_pending,
        },
        "runningJob": running_job,
        "lastAction": (
            None
            if last is None
            else {
                "tsIso": last.tsIso,
                "summary": last.summary,
                "kind": last.kind,
            }
        ),
    }
