"""Queue + gap-analysis helper logic used by the dashboard server.

Important refactor invariant:
- Functions are moved from `server.dashboard_router` verbatim first.
- Call sites are updated to import these functions without behavior changes.
"""

from __future__ import annotations

from contextlib import suppress
from importlib import resources
from pathlib import Path

from fastapi import HTTPException

from github_agent_orchestrator.orchestrator.planning.issue_queue import QUEUE_MARKER_PREFIX
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_get_json,
    _github_patch_json,
    _repo_api_url,
)

# Conventions for orchestrator-created artefacts.
#
# These prefixes are used to (a) detect system-managed workstreams and (b) exclude them
# from unrelated stage heuristics.
_QUEUE_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "review-",  # derived from review docs; handled separately
    "system-",  # system capability updates
    "capability-",
    "capabilities-",
    "maintenance-",
)

_QUEUE_CAPABILITY_PREFIXES: tuple[str, ...] = (
    "system-",
    "capability-",
    "capabilities-",
)

# We control the title of the gap analysis issue, so we can safely detect it by title.
_GAP_ANALYSIS_TITLES: tuple[str, ...] = ("identify the next most important development gap",)


def _queue_filename(path: str) -> str:
    return Path(path).name


def _queue_category_for_filename(filename: str) -> str:
    lowered = filename.lower()
    if lowered.startswith("review-"):
        return "review"
    if lowered.startswith(_QUEUE_CAPABILITY_PREFIXES):
        return "capability"
    if lowered.startswith("gap-"):
        return "gap"
    if lowered.startswith("maintenance-"):
        return "maintenance"
    return "development"


def _is_gap_analysis_issue_title(title: str) -> bool:
    lowered = title.strip().lower()
    if not lowered:
        return False
    return any(lowered == t for t in _GAP_ANALYSIS_TITLES)


_GAP_ANALYSIS_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/gap-analysis.md",
    "planning/issue_templates/gap_analysis.md",
)


def _load_gap_analysis_template_or_raise(
    *, settings: ServerSettings, repo: str, branch: str
) -> str:
    """Load the gap analysis issue template.

    This template is an orchestrator-owned artefact and should NOT be fetched from the target
    repository. Fetching from the target repo is both brittle (template often doesn't exist
    there) and risks reintroducing unsafe prompt mutations.

    We load from the local orchestrator installation (packaged resource) and fall back to a
    local source checkout if running from a git working tree.

    Important: do not fall back to a hard-coded prompt here. Bad fallback prompts can trigger
    runaway self-referential agent behaviour.
    """

    # Keep arguments "used" for ruff's ARG checks, but do not use them for network access.
    _ = (settings, repo, branch)

    # 1) Packaged resource (works for installed distributions).
    with suppress(Exception):
        packaged = resources.files("github_agent_orchestrator.server").joinpath(
            "templates/gap-analysis.md"
        )
        content = packaged.read_text(encoding="utf-8")
        if content.strip():
            return content

    # 2) Local checkout (this repo / source install).
    candidate_roots: list[Path] = [Path.cwd()]
    # Best-effort: in some packaging layouts the parent chain isn't stable.
    with suppress(Exception):
        candidate_roots.append(Path(__file__).resolve().parents[3])

    for root in candidate_roots:
        for template_path in _GAP_ANALYSIS_TEMPLATE_PATHS:
            candidate = root / template_path
            try:
                if candidate.exists() and candidate.is_file():
                    content = candidate.read_text(encoding="utf-8")
                    if content.strip():
                        return content
            except Exception:
                # Keep searching other candidates.
                continue

    raise HTTPException(
        status_code=502,
        detail=(
            "Unable to load gap analysis template from the local orchestrator install. "
            "Expected one of: planning/issue_templates/gap-analysis.md or "
            "planning/issue_templates/gap_analysis.md"
        ),
    )


def _gap_analysis_issue_body_looks_unsafe(body: str) -> bool:
    """Detect unsafe gap-analysis issue bodies.

    We intentionally look for very specific known-bad phrases (from the previous incident)
    to avoid blocking legitimate issue bodies elsewhere.
    """

    lowered = body.lower()
    forbidden = (
        "open a pr that adds exactly one new file",
        "open a pr that adds exactly one new file under /planning/issue_queue/pending/",
        "create one development task in planning/issue_queue/pending/",
    )
    return any(tok in lowered for tok in forbidden)


def _repair_gap_analysis_issue_body_if_unsafe(
    *,
    settings: ServerSettings,
    repo: str,
    issue_number: int,
    branch: str,
    existing_body: str,
) -> bool:
    """Replace an unsafe gap-analysis issue body with the repo template.

    Returns True if a repair was performed.
    """

    if not existing_body.strip():
        return False
    if not _gap_analysis_issue_body_looks_unsafe(existing_body):
        return False

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail=(
                "ORCHESTRATOR_GITHUB_TOKEN is required to repair unsafe gap analysis issue bodies"
            ),
        )

    repaired_body = (
        _load_gap_analysis_template_or_raise(
            settings=settings,
            repo=repo,
            branch=branch,
        ).rstrip()
        + "\n"
    )
    _github_patch_json(
        settings,
        url=_repo_api_url(settings, repository=repo, path=f"issues/{issue_number}"),
        payload={"body": repaired_body},
    )
    return True


def _parse_queue_file_for_issue(*, queue_id: str, raw: str) -> tuple[str, str]:
    """Parse a queue file's raw content into (issue_title, issue_body).

    This mirrors `parse_issue_queue_item` but operates on raw strings.
    """

    lines = raw.splitlines()
    if not lines:
        raise HTTPException(status_code=422, detail=f"Queue file is empty: {queue_id}")

    first = lines[0].rstrip("\n")
    if not first.strip():
        raise HTTPException(
            status_code=422, detail=f"Queue file has an empty first line: {queue_id}"
        )

    title = first
    if title.lstrip().startswith("#"):
        title = title.lstrip().lstrip("#").strip()
    if not title:
        raise HTTPException(
            status_code=422, detail=f"Queue file title resolves to empty: {queue_id}"
        )

    marker = f"<!-- {QUEUE_MARKER_PREFIX} {queue_id} -->"
    body = raw if marker in raw else raw.rstrip() + "\n\n---\n\n" + marker + "\n"

    return title, body


def _search_issue_number_by_queue_marker(
    settings: ServerSettings, *, repository: str, queue_id: str
) -> int | None:
    # Use the search API to find any issue (open or closed) that contains our marker.
    q = f'repo:{repository} "{QUEUE_MARKER_PREFIX} {queue_id}" in:body is:issue'
    data = _github_get_json(
        settings,
        url=f"{settings.github_base_url.rstrip('/')}/search/issues",
        params={"q": q, "per_page": "5"},
    )
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    num = first.get("number")
    return num if isinstance(num, int) else None
