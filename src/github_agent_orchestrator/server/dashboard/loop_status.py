"""Loop status computation and stage reporting for the orchestrator dashboard.

This module contains the logic for computing the orchestrator's current loop stage
from persisted GitHub state (queue files, issues, PRs). It implements the "read side"
of the orchestration loop, providing a UI-friendly status summary without adding new
intelligence or making decisions.

The loop follows stages 1a-3c:
- Stage 1: Gap analysis (build) or Review intake (review)
- Stage 2: Development execution
- Stage 3: Capability updates (build) or Review actions (review)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from github_agent_orchestrator.github_labels import (
    LABEL_REVIEW_CONSUMPTION,
    LABEL_UPDATE_CAPABILITY,
    LABEL_UPDATE_REVIEW,
)
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_get_json,
    _repo_api_url,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    best_match_issue_number as _best_match_issue_number,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    issue_has_label as _issue_has_label,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    linked_pr_numbers_from_issue_timeline as _linked_pr_numbers_from_issue_timeline,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_has_review_request as _pull_request_has_review_request,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_has_review_request_history as _pull_request_has_review_request_history,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_is_merge_candidate as _pull_request_is_merge_candidate,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_pull_request as _get_pull_request,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_repo_text_file as _get_repo_text_file,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_issue_timeline_raw as _list_issue_timeline_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_open_issues_raw as _list_open_issues_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_open_pull_requests_raw as _list_open_pull_requests_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_repo_markdown_files_under as _list_repo_markdown_files_under,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _extract_source_pr_number_from_capability_issue as _extract_source_pr_number_from_capability_issue,
)
from github_agent_orchestrator.server.dashboard.queue_helpers import (
    _GAP_ANALYSIS_TITLES,
    _QUEUE_EXCLUDED_PREFIXES,
    _is_gap_analysis_issue_title,
    _queue_category_for_filename,
    _queue_filename,
)
from github_agent_orchestrator.server.dashboard.text_utilities import (
    _first_markdown_line_as_title,
    _utc_now_iso,
)

STAGE_LABEL_DEVELOPMENT_EXECUTION = "2b — Development execution"


@dataclass(frozen=True)
class IssuePrIndex:
    issue_to_open_prs: dict[int, list[dict[str, Any]]]
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]]


@dataclass(frozen=True)
class QueueStageSignals:
    work_exists: bool
    unpromoted_exists: bool
    ready_exists: bool
    with_pr_exists: bool


@dataclass(frozen=True)
class DevelopmentFocusIndex:
    repo: str
    queue_issue_numbers: dict[str, int | None]
    queue_display_titles: dict[str, str]
    open_issue_titles_by_number: dict[int, str]
    issue_pr_index: IssuePrIndex
    dev_inflight_paths: list[str]
    dev_unpromoted: list[str]
    dev_ready_for_review: list[str]
    dev_with_pr: list[str]
    review_inflight_paths: list[str]
    review_unpromoted: list[str]
    review_ready_for_review: list[str]
    review_with_pr: list[str]


@dataclass(frozen=True)
class FocusInputs:
    repo: str
    loop_mode: str
    stage: str
    gap_issue_nums: list[int]
    cap_issue_nums: list[int]
    review_intake_issue_nums: list[int]
    review_update_issue_nums: list[int]
    open_issue_titles_by_number: dict[int, str]
    gap_index: IssuePrIndex
    cap_index: IssuePrIndex
    review_intake_index: IssuePrIndex
    review_update_index: IssuePrIndex
    dev_index: DevelopmentFocusIndex


@dataclass(frozen=True)
class StageInputs:
    mode: str
    has_open_gap_analysis_issue: bool
    gap_issue_with_pr: bool
    gap_issue_ready_for_review: bool
    cap_issue_nums: list[int]
    cap_issue_with_pr: bool
    cap_issue_ready_for_review: bool
    review_intake_issue_nums: list[int]
    review_intake_with_pr: bool
    review_intake_ready_for_review: bool
    review_update_issue_nums: list[int]
    review_update_with_pr: bool
    review_update_ready_for_review: bool
    review_work_exists: bool
    work_unpromoted_exists: bool
    work_ready_exists: bool
    work_with_pr_exists: bool
    dev_signals: QueueStageSignals
    cap_queue_signals: QueueStageSignals
    processed_count: int


def _first_sorted_path(paths: list[str]) -> str | None:
    if not paths:
        return None
    return sorted(paths)[0]


def _select_preferred_pr(
    *,
    ready_prs: list[dict[str, Any]],
    prs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if ready_prs:
        return ready_prs[0]
    if prs:
        return prs[0]
    return None


def _pr_number_and_url(pr: dict[str, Any] | None) -> tuple[int | None, str | None]:
    if not isinstance(pr, dict):
        return None, None
    pr_num: int | None = None
    pr_url: str | None = None

    raw_pr_num = pr.get("number")
    if isinstance(raw_pr_num, int):
        pr_num = raw_pr_num
    raw_pr_url = pr.get("html_url")
    if isinstance(raw_pr_url, str) and raw_pr_url.strip():
        pr_url = raw_pr_url
    return pr_num, pr_url


def _queue_path_has_associated_open_pr(
    *,
    queue_path: str,
    queue_issue_numbers: dict[str, int | None],
    issue_to_open_prs: dict[int, list[dict[str, Any]]],
) -> bool:
    issue_num = queue_issue_numbers.get(queue_path)
    if issue_num is None:
        return False
    return bool(issue_to_open_prs.get(issue_num))


def _queue_path_has_associated_ready_pr(
    *,
    queue_path: str,
    queue_issue_numbers: dict[str, int | None],
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]],
) -> bool:
    issue_num = queue_issue_numbers.get(queue_path)
    if issue_num is None:
        return False
    return bool(issue_to_open_ready_prs.get(issue_num))


def _queue_file_is_excluded_for_loop_mode(*, filename: str, loop_mode: str) -> bool:
    """Return True if the queue file should be ignored by the active loop mode.

    In build mode, `review-*` artefacts are excluded from the development loop.
    In review mode, `review-*` artefacts are treated as primary work items.
    """

    lowered = (filename or "").lower()
    mode = (loop_mode or "").strip().lower()
    if mode == "review" and lowered.startswith("review-"):
        return False
    return lowered.startswith(_QUEUE_EXCLUDED_PREFIXES)


def _queue_display_title_from_markdown(content: str) -> str:
    display_title = ""
    for raw in (content or "").splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            line = line.lstrip().lstrip("#").strip()
        display_title = line.strip()
        break
    return display_title


def _get_pull_request_cached(
    *,
    settings: ServerSettings,
    repo: str,
    pr_number: int,
    pr_cache: dict[int, dict[str, Any]],
    debug_counters: dict[str, int],
) -> dict[str, Any]:
    cached = pr_cache.get(pr_number)
    if cached is not None:
        return cached
    pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
    pr_cache[pr_number] = pr_data
    debug_counters["pullRequestLookups"] = debug_counters.get("pullRequestLookups", 0) + 1
    return pr_data


def _review_requested_cached(
    *,
    settings: ServerSettings,
    repo: str,
    pr_number: int,
    pr_data: dict[str, Any],
    pr_review_request_cache: dict[int, bool],
    debug_counters: dict[str, int],
) -> bool:
    review_requested = _pull_request_has_review_request(pr_data)
    if review_requested:
        return True

    cached_rr = pr_review_request_cache.get(pr_number)
    if cached_rr is None:
        cached_rr = _pull_request_has_review_request_history(
            settings,
            repository=repo,
            pr_number=pr_number,
        )
        pr_review_request_cache[pr_number] = cached_rr
        debug_counters["issueTimelineLookups"] = debug_counters.get("issueTimelineLookups", 0) + 1
    return bool(cached_rr)


def _issue_open_and_ready_prs(
    *,
    settings: ServerSettings,
    repo: str,
    issue_number: int,
    pr_cache: dict[int, dict[str, Any]],
    pr_review_request_cache: dict[int, bool],
    debug_counters: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_number)
    debug_counters["issueTimelineLookups"] = debug_counters.get("issueTimelineLookups", 0) + 1
    pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

    open_prs: list[dict[str, Any]] = []
    ready_prs: list[dict[str, Any]] = []
    for pr_num in sorted(pr_nums):
        pr_data = _get_pull_request_cached(
            settings=settings,
            repo=repo,
            pr_number=pr_num,
            pr_cache=pr_cache,
            debug_counters=debug_counters,
        )
        if pr_data.get("state") != "open":
            continue
        open_prs.append(pr_data)

        review_requested = _review_requested_cached(
            settings=settings,
            repo=repo,
            pr_number=pr_num,
            pr_data=pr_data,
            pr_review_request_cache=pr_review_request_cache,
            debug_counters=debug_counters,
        )
        if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
            ready_prs.append(pr_data)

    return open_prs, ready_prs


def _issue_pr_lists_for_issue(
    *,
    settings: ServerSettings,
    repo: str,
    issue_num: int,
    pr_cache: dict[int, dict[str, Any]],
    pr_review_request_cache: dict[int, bool],
    debug_counters: dict[str, int],
    precomputed_open_prs: dict[int, list[dict[str, Any]]] | None,
    precomputed_ready_prs: dict[int, list[dict[str, Any]]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_prs = precomputed_open_prs.get(issue_num) if precomputed_open_prs else None
    ready_prs = precomputed_ready_prs.get(issue_num) if precomputed_ready_prs else None
    if open_prs is not None and ready_prs is not None:
        return list(open_prs), list(ready_prs)
    return _issue_open_and_ready_prs(
        settings=settings,
        repo=repo,
        issue_number=issue_num,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
    )


def _issue_pr_maps_and_signals(
    *,
    settings: ServerSettings,
    repo: str,
    issue_numbers: list[int],
    pr_cache: dict[int, dict[str, Any]],
    pr_review_request_cache: dict[int, bool],
    debug_counters: dict[str, int],
    precomputed_open_prs: dict[int, list[dict[str, Any]]] | None = None,
    precomputed_ready_prs: dict[int, list[dict[str, Any]]] | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]], bool, bool]:
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    any_with_pr = False
    any_ready = False
    for issue_num in issue_numbers:
        open_prs_list, ready_prs_list = _issue_pr_lists_for_issue(
            settings=settings,
            repo=repo,
            issue_num=issue_num,
            pr_cache=pr_cache,
            pr_review_request_cache=pr_review_request_cache,
            debug_counters=debug_counters,
            precomputed_open_prs=precomputed_open_prs,
            precomputed_ready_prs=precomputed_ready_prs,
        )
        issue_to_open_prs[issue_num] = open_prs_list
        issue_to_open_ready_prs[issue_num] = ready_prs_list
        any_with_pr = any_with_pr or bool(open_prs_list)
        any_ready = any_ready or bool(ready_prs_list)

    return issue_to_open_prs, issue_to_open_ready_prs, any_with_pr, any_ready


def _queue_issue_and_pr_linkage(
    *,
    settings: ServerSettings,
    repo: str,
    ref: str,
    queue_paths: list[str],
    open_issues_for_matching: list[dict[str, Any]],
    pr_cache: dict[int, dict[str, Any]],
    pr_review_request_cache: dict[int, bool],
    debug_counters: dict[str, int],
) -> tuple[
    dict[str, int | None],
    dict[str, str],
    dict[int, list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
]:
    queue_issue_numbers: dict[str, int | None] = {}
    queue_display_titles: dict[str, str] = {}
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}

    for queue_path in queue_paths:
        content, _sha = _get_repo_text_file(
            settings,
            repository=repo,
            path=queue_path,
            ref=ref,
        )

        display_title = _queue_display_title_from_markdown(content)
        if display_title:
            queue_display_titles[queue_path] = display_title

        title_norm = _first_markdown_line_as_title(content)
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        queue_issue_numbers[queue_path] = issue_num

        if not isinstance(issue_num, int):
            continue
        if issue_num in issue_to_open_prs:
            continue

        open_prs, ready_prs = _issue_open_and_ready_prs(
            settings=settings,
            repo=repo,
            issue_number=issue_num,
            pr_cache=pr_cache,
            pr_review_request_cache=pr_review_request_cache,
            debug_counters=debug_counters,
        )
        issue_to_open_prs[issue_num] = open_prs
        issue_to_open_ready_prs[issue_num] = ready_prs

    return queue_issue_numbers, queue_display_titles, issue_to_open_prs, issue_to_open_ready_prs


def _paths_for_filenames(paths: list[str], filenames: list[str]) -> list[str]:
    wanted = set(filenames)
    return [p for p in paths if _queue_filename(p) in wanted]


def _queue_paths_with_open_pr(
    *,
    queue_paths: list[str],
    queue_issue_numbers: dict[str, int | None],
    issue_to_open_prs: dict[int, list[dict[str, Any]]],
) -> list[str]:
    with_pr: list[str] = []
    for p in queue_paths:
        if _queue_path_has_associated_open_pr(
            queue_path=p,
            queue_issue_numbers=queue_issue_numbers,
            issue_to_open_prs=issue_to_open_prs,
        ):
            with_pr.append(p)
    return with_pr


def _queue_paths_with_ready_pr(
    *,
    queue_paths: list[str],
    queue_issue_numbers: dict[str, int | None],
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]],
) -> list[str]:
    ready: list[str] = []
    for p in queue_paths:
        if _queue_path_has_associated_ready_pr(
            queue_path=p,
            queue_issue_numbers=queue_issue_numbers,
            issue_to_open_ready_prs=issue_to_open_ready_prs,
        ):
            ready.append(p)
    return ready


def _queue_paths_unpromoted(
    *,
    queue_paths: list[str],
    queue_issue_numbers: dict[str, int | None],
) -> list[str]:
    return [p for p in queue_paths if queue_issue_numbers.get(p) is None]


def _queue_paths_promoted_no_pr(
    *,
    queue_paths: list[str],
    queue_issue_numbers: dict[str, int | None],
    issue_to_open_prs: dict[int, list[dict[str, Any]]],
) -> list[str]:
    promoted_no_pr: list[str] = []
    for p in queue_paths:
        issue_num = queue_issue_numbers.get(p)
        if issue_num is None:
            continue
        if not _queue_path_has_associated_open_pr(
            queue_path=p,
            queue_issue_numbers=queue_issue_numbers,
            issue_to_open_prs=issue_to_open_prs,
        ):
            promoted_no_pr.append(p)
    return promoted_no_pr


def _stage_for_review_intake_issue(
    *,
    review_intake_issue_nums: list[int],
    review_intake_with_pr: bool,
    review_intake_ready_for_review: bool,
) -> tuple[str, str, int, str] | None:
    if not review_intake_issue_nums:
        return None
    if review_intake_ready_for_review:
        return (
            "1c",
            "1c — Review intake PR ready for merge",
            2,
            "open review intake issue has an associated open PR ready for review",
        )
    if review_intake_with_pr:
        return (
            "1b",
            "1b — Review intake execution",
            1,
            "open review intake issue has an associated open PR",
        )
    return (
        "1a",
        "1a — Review intake issue",
        0,
        "open review intake issue detected (no PR yet)",
    )


def _stage_for_review_update_issue(
    *,
    review_update_issue_nums: list[int],
    review_update_with_pr: bool,
    review_update_ready_for_review: bool,
) -> tuple[str, str, int, str] | None:
    if not review_update_issue_nums:
        return None
    if review_update_ready_for_review:
        return (
            "3c",
            "3c — Review actions PR ready for merge",
            8,
            "open review update issue has an associated open PR ready for review",
        )
    if review_update_with_pr:
        return (
            "3b",
            "3b — Review actions update execution",
            7,
            "open review update issue has an associated open PR",
        )
    return (
        "3a",
        "3a — Review actions update issue",
        6,
        "open review update issue exists (no PR yet)",
    )


def _stage_for_review_work_queue(
    *,
    work_unpromoted_exists: bool,
    work_ready_exists: bool,
    work_with_pr_exists: bool,
) -> tuple[str, str, int, str]:
    if work_unpromoted_exists:
        return (
            "2a",
            "2a — Development issue creation",
            3,
            "pending work queue file(s) exist without an associated open issue",
        )
    if work_ready_exists:
        return (
            "2c",
            "2c — Development PR ready for merge",
            5,
            "work has an open PR with review requested and no conflicts",
        )
    reason = "pending work queue file(s) have an associated open issue but no PR yet"
    if work_with_pr_exists:
        reason = "pending work queue file(s) have an associated open PR"
    return ("2b", STAGE_LABEL_DEVELOPMENT_EXECUTION, 4, reason)


def _stage_for_gap_analysis_issue(
    *,
    has_open_gap_analysis_issue: bool,
    gap_issue_with_pr: bool,
    gap_issue_ready_for_review: bool,
) -> tuple[str, str, int, str] | None:
    if not has_open_gap_analysis_issue:
        return None
    if gap_issue_ready_for_review:
        return (
            "1c",
            "1c — Gap analysis PR ready for merge",
            2,
            "open gap analysis issue has an associated open PR ready for review",
        )
    if gap_issue_with_pr:
        return (
            "1b",
            "1b — Gap analysis execution",
            1,
            "open gap analysis issue has an associated open PR",
        )
    return (
        "1a",
        "1a — Gap analysis issue",
        0,
        "open gap analysis issue detected (no PR yet)",
    )


def _stage_for_capability_issue(
    *,
    cap_issue_nums: list[int],
    cap_issue_with_pr: bool,
    cap_issue_ready_for_review: bool,
) -> tuple[str, str, int, str] | None:
    if not cap_issue_nums:
        return None
    if cap_issue_ready_for_review:
        return (
            "3c",
            "3c — Capability PR ready for merge",
            8,
            "open capability update issue exists and has an associated open PR ready for review",
        )
    if cap_issue_with_pr:
        return (
            "3b",
            "3b — Capability update execution",
            7,
            "open capability update issue exists and has an associated open PR",
        )
    return ("3a", "3a — Capability update issue", 6, "open capability update issue exists (no PR yet)")


def _stage_for_development_queue(dev_signals: QueueStageSignals) -> tuple[str, str, int, str] | None:
    if not dev_signals.work_exists:
        return None
    if dev_signals.unpromoted_exists:
        return (
            "2a",
            "2a — Development issue creation",
            3,
            "pending development queue file(s) exist without an associated open issue",
        )
    if dev_signals.ready_exists:
        return (
            "2c",
            "2c — Development PR ready for merge",
            5,
            "development work has an open PR with review requested and no conflicts",
        )
    reason = "pending development queue file(s) have an associated open issue but no PR yet"
    if dev_signals.with_pr_exists:
        reason = "pending development queue file(s) have an associated open PR"
    return ("2b", STAGE_LABEL_DEVELOPMENT_EXECUTION, 4, reason)


def _stage_for_capability_queue(
    cap_queue_signals: QueueStageSignals,
) -> tuple[str, str, int, str] | None:
    if not cap_queue_signals.work_exists:
        return None
    if cap_queue_signals.unpromoted_exists:
        return (
            "3a",
            "3a — Capability update queued",
            6,
            "pending capability update queue file(s) exist without an associated open issue",
        )
    if cap_queue_signals.ready_exists:
        return (
            "3c",
            "3c — Capability PR ready for merge",
            8,
            "pending capability update queue file(s) have an associated ready PR",
        )
    return (
        "3b",
        "3b — Capability update in progress",
        7,
        "pending capability update queue file(s) have an associated open PR",
    )


def _select_review_stage(
    *,
    review_intake_issue_nums: list[int],
    review_intake_with_pr: bool,
    review_intake_ready_for_review: bool,
    review_update_issue_nums: list[int],
    review_update_with_pr: bool,
    review_update_ready_for_review: bool,
    review_work_exists: bool,
    work_unpromoted_exists: bool,
    work_ready_exists: bool,
    work_with_pr_exists: bool,
    processed_count: int,
) -> tuple[str, str, int, str]:
    stage = _stage_for_review_intake_issue(
        review_intake_issue_nums=review_intake_issue_nums,
        review_intake_with_pr=review_intake_with_pr,
        review_intake_ready_for_review=review_intake_ready_for_review,
    )
    if stage is not None:
        return stage

    stage = _stage_for_review_update_issue(
        review_update_issue_nums=review_update_issue_nums,
        review_update_with_pr=review_update_with_pr,
        review_update_ready_for_review=review_update_ready_for_review,
    )
    if stage is not None:
        return stage

    if review_work_exists:
        return _stage_for_review_work_queue(
            work_unpromoted_exists=work_unpromoted_exists,
            work_ready_exists=work_ready_exists,
            work_with_pr_exists=work_with_pr_exists,
        )

    if processed_count > 0:
        return ("2b", STAGE_LABEL_DEVELOPMENT_EXECUTION, 4, "processed queue artefacts exist")

    return ("1a", "1a — Review intake issue", 0, "no pending/processed artefacts")


def _select_build_stage(
    *,
    has_open_gap_analysis_issue: bool,
    gap_issue_with_pr: bool,
    gap_issue_ready_for_review: bool,
    cap_issue_nums: list[int],
    cap_issue_with_pr: bool,
    cap_issue_ready_for_review: bool,
    dev_signals: QueueStageSignals,
    cap_queue_signals: QueueStageSignals,
    processed_count: int,
) -> tuple[str, str, int, str]:
    stage = _stage_for_gap_analysis_issue(
        has_open_gap_analysis_issue=has_open_gap_analysis_issue,
        gap_issue_with_pr=gap_issue_with_pr,
        gap_issue_ready_for_review=gap_issue_ready_for_review,
    )
    if stage is not None:
        return stage

    stage = _stage_for_capability_issue(
        cap_issue_nums=cap_issue_nums,
        cap_issue_with_pr=cap_issue_with_pr,
        cap_issue_ready_for_review=cap_issue_ready_for_review,
    )
    if stage is not None:
        return stage

    stage = _stage_for_development_queue(dev_signals)
    if stage is not None:
        return stage

    stage = _stage_for_capability_queue(cap_queue_signals)
    if stage is not None:
        return stage

    if processed_count > 0:
        return ("2b", STAGE_LABEL_DEVELOPMENT_EXECUTION, 4, "processed queue artefacts exist")
    return ("1a", "1a — Gap analysis issue", 0, "no pending/processed artefacts")


def _base_warnings(loop_mode: str) -> list[str]:
    warnings: list[str] = []
    warnings.append(
        "Loop status is derived exclusively from git-tracked files in the target repository; "
        "no local JSON stores are consulted."
    )
    warnings.append(
        "Pending queue files are associated to GitHub issues by matching the file title (first line) "
        "against open issue titles; PR association is derived from issue cross-references in GitHub."
    )
    warnings.append(
        f"Capability update issues are detected by the '{LABEL_UPDATE_CAPABILITY}' label (open issues)."
    )
    if loop_mode == "review":
        warnings.append(
            f"Review intake issues are detected by the '{LABEL_REVIEW_CONSUMPTION}' label (open issues)."
        )
        warnings.append(
            f"Review update issues are detected by the '{LABEL_UPDATE_REVIEW}' label (open issues)."
        )
    return warnings


def _focus_for_labeled_issue(
    *,
    kind: str,
    repo: str,
    issue_num: int,
    title: str,
    pr_index: IssuePrIndex,
    make_issue_url: Any,
) -> dict[str, object]:
    prs = pr_index.issue_to_open_prs.get(issue_num) or []
    ready_prs = pr_index.issue_to_open_ready_prs.get(issue_num) or []
    selected_pr = _select_preferred_pr(ready_prs=ready_prs, prs=prs)
    pr_num, pr_url = _pr_number_and_url(selected_pr)
    return {
        "kind": kind,
        "title": title,
        "issueNumber": issue_num,
        "issueUrl": make_issue_url(repo, issue_num),
        "pullNumber": pr_num,
        "pullUrl": pr_url,
    }


def _focus_for_development(
    *,
    stage: str,
    loop_mode: str,
    index: DevelopmentFocusIndex,
    make_issue_url: Any,
) -> dict[str, object] | None:
    if loop_mode == "review":
        inflight_paths = index.review_inflight_paths + index.dev_inflight_paths
        unpromoted_paths = index.review_unpromoted + index.dev_unpromoted
        ready_paths = index.review_ready_for_review + index.dev_ready_for_review
        with_pr_paths = index.review_with_pr + index.dev_with_pr
    else:
        inflight_paths = index.dev_inflight_paths
        unpromoted_paths = index.dev_unpromoted
        ready_paths = index.dev_ready_for_review
        with_pr_paths = index.dev_with_pr

    if stage == "2a":
        focus_path = _first_sorted_path(unpromoted_paths)
    elif stage == "2c":
        focus_path = _first_sorted_path(ready_paths)
    else:
        focus_path = _first_sorted_path(with_pr_paths) or _first_sorted_path(inflight_paths)

    if not focus_path:
        return None

    issue_num = index.queue_issue_numbers.get(focus_path)
    focus_pr_num: int | None = None
    focus_pr_url: str | None = None
    if isinstance(issue_num, int):
        prs = index.issue_pr_index.issue_to_open_prs.get(issue_num) or []
        ready_prs = index.issue_pr_index.issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = _select_preferred_pr(ready_prs=ready_prs, prs=prs)
        focus_pr_num, focus_pr_url = _pr_number_and_url(selected_pr)

    title = index.queue_display_titles.get(focus_path) or ""
    if isinstance(issue_num, int) and issue_num in index.open_issue_titles_by_number:
        title = index.open_issue_titles_by_number.get(issue_num) or title

    return {
        "kind": "development",
        "queuePath": focus_path,
        "queueId": _queue_filename(focus_path),
        "title": title,
        "issueNumber": issue_num,
        "issueUrl": make_issue_url(index.repo, int(issue_num)) if isinstance(issue_num, int) else None,
        "pullNumber": focus_pr_num,
        "pullUrl": focus_pr_url,
    }


def _focus_for_capability(
    *,
    settings: ServerSettings,
    repo: str,
    issue_num: int,
    title: str,
    cap_issue_to_open_prs: dict[int, list[dict[str, Any]]],
    cap_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]],
    make_issue_url: Any,
) -> dict[str, object]:
    issue_body = ""
    issue_title_for_parse = title
    try:
        issue_data = _github_get_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{issue_num}"),
        )
        raw_body = issue_data.get("body")
        raw_title = issue_data.get("title")
        if isinstance(raw_body, str):
            issue_body = raw_body
        if isinstance(raw_title, str) and raw_title.strip():
            issue_title_for_parse = raw_title
    except HTTPException:
        issue_body = ""

    source_pr_number = _extract_source_pr_number_from_capability_issue(
        repository=repo,
        issue_title=issue_title_for_parse,
        issue_body=issue_body,
    )
    source_pr_title: str | None = None
    source_pr_url: str | None = None
    if isinstance(source_pr_number, int):
        try:
            source_pr = _get_pull_request(
                settings,
                repository=repo,
                pr_number=source_pr_number,
            )
            raw_title = source_pr.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                source_pr_title = raw_title
            raw_url = source_pr.get("html_url")
            if isinstance(raw_url, str) and raw_url.strip():
                source_pr_url = raw_url
        except HTTPException:
            source_pr_title = None
            source_pr_url = None

    prs = cap_issue_to_open_prs.get(issue_num) or []
    ready_prs = cap_issue_to_open_ready_prs.get(issue_num) or []
    selected_pr = _select_preferred_pr(ready_prs=ready_prs, prs=prs)
    pr_num, pr_url = _pr_number_and_url(selected_pr)

    return {
        "kind": "capability",
        "title": title,
        "issueNumber": issue_num,
        "issueUrl": make_issue_url(repo, issue_num),
        "pullNumber": pr_num,
        "pullUrl": pr_url,
        "sourceTitle": source_pr_title,
        "sourcePullNumber": source_pr_number,
        "sourcePullUrl": source_pr_url,
    }


def _select_focus(
    *,
    settings: ServerSettings,
    inputs: FocusInputs,
    make_issue_url: Any,
) -> dict[str, object] | None:
    if inputs.loop_mode == "review" and inputs.stage in {"1a", "1b", "1c"} and inputs.review_intake_issue_nums:
        issue_num = sorted(inputs.review_intake_issue_nums)[0]
        title = inputs.open_issue_titles_by_number.get(issue_num) or ""
        return _focus_for_labeled_issue(
            kind="review",
            repo=inputs.repo,
            issue_num=issue_num,
            title=title,
            pr_index=inputs.review_intake_index,
            make_issue_url=make_issue_url,
        )

    if inputs.loop_mode == "review" and inputs.stage in {"3a", "3b", "3c"} and inputs.review_update_issue_nums:
        issue_num = sorted(inputs.review_update_issue_nums)[0]
        title = inputs.open_issue_titles_by_number.get(issue_num) or ""
        return _focus_for_labeled_issue(
            kind="reviewUpdate",
            repo=inputs.repo,
            issue_num=issue_num,
            title=title,
            pr_index=inputs.review_update_index,
            make_issue_url=make_issue_url,
        )

    if inputs.stage in {"1a", "1b", "1c"} and inputs.gap_issue_nums:
        issue_num = inputs.gap_issue_nums[0]
        title = inputs.open_issue_titles_by_number.get(issue_num) or ""
        return _focus_for_labeled_issue(
            kind="gap",
            repo=inputs.repo,
            issue_num=issue_num,
            title=title,
            pr_index=inputs.gap_index,
            make_issue_url=make_issue_url,
        )

    if inputs.stage in {"2a", "2b", "2c"}:
        return _focus_for_development(
            stage=inputs.stage,
            loop_mode=inputs.loop_mode,
            index=inputs.dev_index,
            make_issue_url=make_issue_url,
        )

    if inputs.stage in {"3a", "3b", "3c"} and inputs.cap_issue_nums:
        issue_num = sorted(inputs.cap_issue_nums)[0]
        title = inputs.open_issue_titles_by_number.get(issue_num) or ""
        return _focus_for_capability(
            settings=settings,
            repo=inputs.repo,
            issue_num=issue_num,
            title=title,
            cap_issue_to_open_prs=inputs.cap_index.issue_to_open_prs,
            cap_issue_to_open_ready_prs=inputs.cap_index.issue_to_open_ready_prs,
            make_issue_url=make_issue_url,
        )

    return None


def loop_status(request: Request) -> dict[str, object]:
    """Return a UI-friendly summary of the orchestrator's 1a–3c loop.

    The intent is to help visualize where the system currently is *without* adding
    new "intelligence". This is a best-effort stage derived from persisted state.
    """

    from github_agent_orchestrator.server import dashboard_router

    settings = dashboard_router._settings(request)

    repo_param = request.query_params.get("repo", "").strip()
    active_repo = repo_param or settings.default_repo.strip()
    if not active_repo:
        raise HTTPException(
            status_code=409,
            detail="repo is required (pass ?repo=owner/name or set ORCHESTRATOR_DEFAULT_REPO)",
        )

    ref = request.query_params.get("ref", "").strip()
    return _loop_status_for_repo(settings=settings, active_repo=active_repo, ref=ref)


def _queue_filenames(paths: list[str]) -> list[str]:
    return [_queue_filename(p) for p in paths]


def _queue_files_by_category(filenames: list[str]) -> dict[str, list[str]]:
    by_category: dict[str, list[str]] = {}
    for filename in filenames:
        by_category.setdefault(_queue_category_for_filename(filename), []).append(filename)
    return by_category


def _excluded_queue_filenames(*, filenames: list[str], loop_mode: str) -> list[str]:
    return [
        f for f in filenames if _queue_file_is_excluded_for_loop_mode(filename=f, loop_mode=loop_mode)
    ]


def _non_pr_issue_dicts(raw_issues: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    return [it for it in raw_issues if isinstance(it, dict) and "pull_request" not in it]


def _issue_titles_and_map(issues: list[dict[str, Any]]) -> tuple[list[str], dict[int, str]]:
    titles: list[str] = []
    titles_by_number: dict[int, str] = {}
    for it in issues:
        num = it.get("number")
        title = it.get("title")
        if isinstance(title, str):
            titles.append(title)
            if isinstance(num, int):
                titles_by_number[num] = title
    return titles, titles_by_number


def _issue_numbers_with_label(issues: list[dict[str, Any]], *, label_name: str) -> list[int]:
    return [
        int(it["number"])
        for it in issues
        if isinstance(it.get("number"), int) and _issue_has_label(it, label_name=label_name)
    ]


def _gap_analysis_issue_numbers(issues: list[dict[str, Any]]) -> list[int]:
    return [
        int(it["number"])
        for it in issues
        if isinstance(it.get("number"), int)
        and isinstance(it.get("title"), str)
        and _is_gap_analysis_issue_title(str(it.get("title")))
    ]


def _select_stage_for_mode(*, inputs: StageInputs) -> tuple[str, str, int, str]:
    if inputs.mode == "review":
        return _select_review_stage(
            review_intake_issue_nums=inputs.review_intake_issue_nums,
            review_intake_with_pr=inputs.review_intake_with_pr,
            review_intake_ready_for_review=inputs.review_intake_ready_for_review,
            review_update_issue_nums=inputs.review_update_issue_nums,
            review_update_with_pr=inputs.review_update_with_pr,
            review_update_ready_for_review=inputs.review_update_ready_for_review,
            review_work_exists=inputs.review_work_exists,
            work_unpromoted_exists=inputs.work_unpromoted_exists,
            work_ready_exists=inputs.work_ready_exists,
            work_with_pr_exists=inputs.work_with_pr_exists,
            processed_count=inputs.processed_count,
        )
    return _select_build_stage(
        has_open_gap_analysis_issue=inputs.has_open_gap_analysis_issue,
        gap_issue_with_pr=inputs.gap_issue_with_pr,
        gap_issue_ready_for_review=inputs.gap_issue_ready_for_review,
        cap_issue_nums=inputs.cap_issue_nums,
        cap_issue_with_pr=inputs.cap_issue_with_pr,
        cap_issue_ready_for_review=inputs.cap_issue_ready_for_review,
        dev_signals=inputs.dev_signals,
        cap_queue_signals=inputs.cap_queue_signals,
        processed_count=inputs.processed_count,
    )


def _apply_best_effort_automations(
    *,
    settings: ServerSettings,
    active_repo: str,
    focus: dict[str, object] | None,
    raw_open_prs: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    if not isinstance(focus, dict):
        return

    from github_agent_orchestrator.server.dashboard.automation_auto_link import (
        maybe_auto_link_focused_issue_to_pr as _maybe_auto_link_focused_issue_to_pr,
    )

    link_msg = _maybe_auto_link_focused_issue_to_pr(
        settings=settings,
        repository=active_repo,
        focus=focus,
        raw_open_prs=raw_open_prs,
    )
    if isinstance(link_msg, str) and link_msg.strip():
        warnings.append(link_msg)

    if not settings.auto_resume_copilot_on_rate_limit:
        return
    focus_pull_number = focus.get("pullNumber")
    if not (isinstance(focus_pull_number, int) and focus_pull_number > 0):
        return

    from github_agent_orchestrator.server.dashboard.automation_auto_resume import (
        maybe_auto_resume_copilot_after_rate_limit as _maybe_auto_resume_copilot_after_rate_limit,
    )

    msg = _maybe_auto_resume_copilot_after_rate_limit(
        settings=settings,
        repository=active_repo,
        pr_number=focus_pull_number,
    )
    if isinstance(msg, str) and msg.strip():
        warnings.append(msg)


def _loop_status_for_repo(
    *, settings: ServerSettings, active_repo: str, ref: str
) -> dict[str, object]:
    from github_agent_orchestrator.server import dashboard_router

    mode = getattr(settings, "loop_mode", "build")
    target_state_missing = False
    try:
        _get_repo_text_file(
            settings=settings,
            repository=active_repo,
            path=".agent-orchestrator/state/target_state.md",
            ref=ref,
        )
    except HTTPException:
        target_state_missing = True

    if target_state_missing:
        warnings = _base_warnings(mode)
        warnings.append(
            "Target state is missing. Create /.agent-orchestrator/state/target_state.md before the loop can run."
        )
        return {
            "nowIso": _utc_now_iso(),
            "repo": active_repo,
            "ref": (ref or None),
            "loopMode": mode,
            "stage": "1a",
            "stageLabel": "1a — Gap analysis issue",
            "activeStep": 0,
            "stageReason": "waiting for target_state.md",
            "sources": {
                "queueCounts": "github_git_tree",
            },
            "counts": {
                "pending": 0,
                "processed": 0,
                "complete": 0,
                "openIssues": 0,
                "openPullRequests": 0,
                "openGapAnalysisIssues": 0,
                "openGapAnalysisIssuesWithPr": 0,
                "openGapAnalysisIssuesReadyForReview": 0,
                "openReviewConsumptionIssues": 0,
                "openReviewUpdateIssues": 0,
                "unpromotedPending": 0,
                "pendingDevelopment": 0,
                "pendingReview": 0,
                "pendingCapabilityUpdates": 0,
                "pendingExcluded": 0,
                "pendingDevelopmentWithoutPr": 0,
                "pendingDevelopmentWithPr": 0,
                "pendingDevelopmentReadyForReview": 0,
                "pendingReviewWithoutPr": 0,
                "pendingReviewWithPr": 0,
                "pendingReviewReadyForReview": 0,
                "pendingCapabilityUpdatesWithoutPr": 0,
                "pendingCapabilityUpdatesWithPr": 0,
                "pendingCapabilityUpdatesReadyForReview": 0,
                "openCapabilityUpdateIssues": 0,
                "openCapabilityUpdateIssuesWithPr": 0,
                "openCapabilityUpdateIssuesReadyForReview": 0,
            },
            "debug": {
                "pendingQueueFilesSample": [],
                "processedQueueFilesSample": [],
                "completeQueueFilesSample": [],
                "pendingExcludedPrefixes": list(_QUEUE_EXCLUDED_PREFIXES),
                "gapAnalysisIssueTitles": list(_GAP_ANALYSIS_TITLES),
                "issueTimelineLookups": 0,
                "pullRequestLookups": 0,
            },
            "warnings": warnings,
            "focus": None,
            "runningJob": None,
            "lastAction": None,
        }
    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path=".agent-orchestrator/issue_queue/pending",
        ref=ref,
    )
    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path=".agent-orchestrator/issue_queue/processed",
        ref=ref,
    )
    complete_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path=".agent-orchestrator/issue_queue/complete",
        ref=ref,
    )

    pending_count = len(pending_paths)
    processed_count = len(processed_paths)
    complete_count = len(complete_paths)

    # --- GitHub repo-derived signals (no local checkout/state) ---
    raw_issues = _list_open_issues_raw(settings, repository=active_repo)
    open_issue_dicts = _non_pr_issue_dicts(raw_issues)
    open_issue_titles, open_issue_titles_by_number = _issue_titles_and_map(open_issue_dicts)
    open_capability_issue_numbers = _issue_numbers_with_label(
        open_issue_dicts, label_name=LABEL_UPDATE_CAPABILITY
    )
    open_review_update_issue_numbers = _issue_numbers_with_label(
        open_issue_dicts, label_name=LABEL_UPDATE_REVIEW
    )
    open_review_consumption_issue_numbers = _issue_numbers_with_label(
        open_issue_dicts, label_name=LABEL_REVIEW_CONSUMPTION
    )
    gap_issue_nums = sorted(set(_gap_analysis_issue_numbers(open_issue_dicts)))
    has_open_gap_analysis_issue = bool(gap_issue_nums)

    raw_open_prs = _list_open_pull_requests_raw(settings, repository=active_repo, limit=100)
    open_pr_count = len(raw_open_prs)

    pending_files = _queue_filenames(pending_paths)
    pending_by_category = _queue_files_by_category(pending_files)

    dev_pending = pending_by_category.get("development", [])
    review_pending = pending_by_category.get("review", [])
    cap_pending = pending_by_category.get("capability", [])
    excluded_pending = _excluded_queue_filenames(filenames=pending_files, loop_mode=mode)

    processed_files = _queue_filenames(processed_paths)
    processed_by_category = _queue_files_by_category(processed_files)

    dev_processed = processed_by_category.get("development", [])
    review_processed = processed_by_category.get("review", [])
    cap_processed = processed_by_category.get("capability", [])

    # Associate queue files (pending + processed) -> GitHub issues by matching the file title
    # (first line) to open issue titles. Then associate issues -> PRs via issue timeline events.
    open_issues_for_matching = list(open_issue_dicts)
    pr_cache: dict[int, dict[str, Any]] = {}
    pr_review_request_cache: dict[int, bool] = {}
    debug_counters: dict[str, int] = {"issueTimelineLookups": 0, "pullRequestLookups": 0}

    queue_paths_for_linkage = list(pending_paths) + list(processed_paths)
    (
        queue_issue_numbers,
        queue_display_titles,
        issue_to_open_prs,
        issue_to_open_ready_prs,
    ) = _queue_issue_and_pr_linkage(
        settings=settings,
        repo=active_repo,
        ref=ref,
        queue_paths=queue_paths_for_linkage,
        open_issues_for_matching=open_issues_for_matching,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
    )

    # Capability update issues (Step E/F/G) are derived from labels, not queue files.
    cap_issue_nums = sorted(set(open_capability_issue_numbers))
    (
        cap_issue_to_open_prs,
        cap_issue_to_open_ready_prs,
        cap_issue_with_pr,
        cap_issue_ready_for_review,
    ) = _issue_pr_maps_and_signals(
        settings=settings,
        repo=active_repo,
        issue_numbers=cap_issue_nums,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
        precomputed_open_prs=issue_to_open_prs,
        precomputed_ready_prs=issue_to_open_ready_prs,
    )

    # Gap-analysis issues (Step A) are derived from titles, not queue artefacts.
    (
        gap_issue_to_open_prs,
        gap_issue_to_open_ready_prs,
        gap_issue_with_pr,
        gap_issue_ready_for_review,
    ) = _issue_pr_maps_and_signals(
        settings=settings,
        repo=active_repo,
        issue_numbers=gap_issue_nums,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
        precomputed_open_prs=issue_to_open_prs,
        precomputed_ready_prs=issue_to_open_ready_prs,
    )

    # Review-mode issues are derived from labels.
    review_intake_issue_nums = sorted(set(open_review_consumption_issue_numbers))
    review_update_issue_nums = sorted(set(open_review_update_issue_numbers))

    (
        review_intake_issue_to_open_prs,
        review_intake_issue_to_open_ready_prs,
        review_intake_with_pr,
        review_intake_ready_for_review,
    ) = _issue_pr_maps_and_signals(
        settings=settings,
        repo=active_repo,
        issue_numbers=review_intake_issue_nums,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
        precomputed_open_prs=issue_to_open_prs,
        precomputed_ready_prs=issue_to_open_ready_prs,
    )

    (
        review_update_issue_to_open_prs,
        review_update_issue_to_open_ready_prs,
        review_update_with_pr,
        review_update_ready_for_review,
    ) = _issue_pr_maps_and_signals(
        settings=settings,
        repo=active_repo,
        issue_numbers=review_update_issue_nums,
        pr_cache=pr_cache,
        pr_review_request_cache=pr_review_request_cache,
        debug_counters=debug_counters,
        precomputed_open_prs=issue_to_open_prs,
        precomputed_ready_prs=issue_to_open_ready_prs,
    )

    dev_pending_paths = _paths_for_filenames(pending_paths, dev_pending)
    review_pending_paths = _paths_for_filenames(pending_paths, review_pending)
    cap_pending_paths = _paths_for_filenames(pending_paths, cap_pending)
    dev_processed_paths = _paths_for_filenames(processed_paths, dev_processed)
    review_processed_paths = _paths_for_filenames(processed_paths, review_processed)
    cap_processed_paths = _paths_for_filenames(processed_paths, cap_processed)

    dev_inflight_paths = dev_pending_paths + dev_processed_paths
    review_inflight_paths = review_pending_paths + review_processed_paths
    cap_inflight_paths = cap_pending_paths + cap_processed_paths

    dev_with_pr = _queue_paths_with_open_pr(
        queue_paths=dev_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )
    dev_ready_for_review = _queue_paths_with_ready_pr(
        queue_paths=dev_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_ready_prs=issue_to_open_ready_prs,
    )
    review_with_pr = _queue_paths_with_open_pr(
        queue_paths=review_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )
    review_ready_for_review = _queue_paths_with_ready_pr(
        queue_paths=review_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_ready_prs=issue_to_open_ready_prs,
    )

    cap_with_pr = _queue_paths_with_open_pr(
        queue_paths=cap_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )
    cap_ready_for_review = _queue_paths_with_ready_pr(
        queue_paths=cap_inflight_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_ready_prs=issue_to_open_ready_prs,
    )

    dev_unpromoted = _queue_paths_unpromoted(
        queue_paths=dev_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
    )
    review_unpromoted = _queue_paths_unpromoted(
        queue_paths=review_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
    )
    dev_promoted_no_pr = _queue_paths_promoted_no_pr(
        queue_paths=dev_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )
    review_promoted_no_pr = _queue_paths_promoted_no_pr(
        queue_paths=review_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )
    cap_unpromoted = _queue_paths_unpromoted(
        queue_paths=cap_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
    )
    cap_promoted_no_pr = _queue_paths_promoted_no_pr(
        queue_paths=cap_pending_paths,
        queue_issue_numbers=queue_issue_numbers,
        issue_to_open_prs=issue_to_open_prs,
    )

    # --- Stage selection (priority is loop order) ---
    review_work_exists = bool(review_pending or review_processed or dev_pending or dev_processed)
    dev_signals = QueueStageSignals(
        work_exists=bool(dev_pending or dev_processed),
        unpromoted_exists=bool(dev_unpromoted),
        ready_exists=bool(dev_ready_for_review),
        with_pr_exists=bool(dev_with_pr),
    )
    cap_queue_signals = QueueStageSignals(
        work_exists=bool(cap_pending or cap_processed),
        unpromoted_exists=bool(cap_unpromoted),
        ready_exists=bool(cap_ready_for_review),
        with_pr_exists=bool(cap_with_pr),
    )
    stage_inputs = StageInputs(
        mode=mode,
        has_open_gap_analysis_issue=has_open_gap_analysis_issue,
        gap_issue_with_pr=gap_issue_with_pr,
        gap_issue_ready_for_review=gap_issue_ready_for_review,
        cap_issue_nums=cap_issue_nums,
        cap_issue_with_pr=cap_issue_with_pr,
        cap_issue_ready_for_review=cap_issue_ready_for_review,
        review_intake_issue_nums=review_intake_issue_nums,
        review_intake_with_pr=review_intake_with_pr,
        review_intake_ready_for_review=review_intake_ready_for_review,
        review_update_issue_nums=review_update_issue_nums,
        review_update_with_pr=review_update_with_pr,
        review_update_ready_for_review=review_update_ready_for_review,
        review_work_exists=review_work_exists,
        work_unpromoted_exists=bool(review_unpromoted or dev_unpromoted),
        work_ready_exists=bool(review_ready_for_review or dev_ready_for_review),
        work_with_pr_exists=bool(review_with_pr or dev_with_pr),
        dev_signals=dev_signals,
        cap_queue_signals=cap_queue_signals,
        processed_count=processed_count,
    )
    stage, stage_label, active_step, stage_reason = _select_stage_for_mode(inputs=stage_inputs)

    warnings = _base_warnings(mode)

    dev_index = DevelopmentFocusIndex(
        repo=active_repo,
        queue_issue_numbers=queue_issue_numbers,
        queue_display_titles=queue_display_titles,
        open_issue_titles_by_number=open_issue_titles_by_number,
        issue_pr_index=IssuePrIndex(
            issue_to_open_prs=issue_to_open_prs,
            issue_to_open_ready_prs=issue_to_open_ready_prs,
        ),
        dev_inflight_paths=dev_inflight_paths,
        dev_unpromoted=dev_unpromoted,
        dev_ready_for_review=dev_ready_for_review,
        dev_with_pr=dev_with_pr,
        review_inflight_paths=review_inflight_paths,
        review_unpromoted=review_unpromoted,
        review_ready_for_review=review_ready_for_review,
        review_with_pr=review_with_pr,
    )

    focus_inputs = FocusInputs(
        repo=active_repo,
        loop_mode=mode,
        stage=stage,
        gap_issue_nums=gap_issue_nums,
        cap_issue_nums=cap_issue_nums,
        review_intake_issue_nums=review_intake_issue_nums,
        review_update_issue_nums=review_update_issue_nums,
        open_issue_titles_by_number=open_issue_titles_by_number,
        gap_index=IssuePrIndex(
            issue_to_open_prs=gap_issue_to_open_prs,
            issue_to_open_ready_prs=gap_issue_to_open_ready_prs,
        ),
        cap_index=IssuePrIndex(
            issue_to_open_prs=cap_issue_to_open_prs,
            issue_to_open_ready_prs=cap_issue_to_open_ready_prs,
        ),
        review_intake_index=IssuePrIndex(
            issue_to_open_prs=review_intake_issue_to_open_prs,
            issue_to_open_ready_prs=review_intake_issue_to_open_ready_prs,
        ),
        review_update_index=IssuePrIndex(
            issue_to_open_prs=review_update_issue_to_open_prs,
            issue_to_open_ready_prs=review_update_issue_to_open_ready_prs,
        ),
        dev_index=dev_index,
    )

    focus = _select_focus(
        settings=settings,
        inputs=focus_inputs,
        make_issue_url=dashboard_router._make_github_issue_url,
    )

    _apply_best_effort_automations(
        settings=settings,
        active_repo=active_repo,
        focus=focus if isinstance(focus, dict) else None,
        raw_open_prs=raw_open_prs,
        warnings=warnings,
    )

    return {
        "nowIso": _utc_now_iso(),
        "repo": active_repo,
        "ref": (ref or None),
        "loopMode": mode,
        "stage": stage,
        "stageLabel": stage_label,
        "activeStep": active_step,
        "stageReason": stage_reason,
        "sources": {
            "queueCounts": "github_git_tree",
        },
        "counts": {
            "pending": pending_count,
            "processed": processed_count,
            "complete": complete_count,
            "openIssues": len(open_issue_titles),
            "openPullRequests": open_pr_count,
            "openGapAnalysisIssues": len(gap_issue_nums),
            "openGapAnalysisIssuesWithPr": (1 if gap_issue_with_pr else 0),
            "openGapAnalysisIssuesReadyForReview": (1 if gap_issue_ready_for_review else 0),
            "openReviewConsumptionIssues": len(set(open_review_consumption_issue_numbers)),
            "openReviewUpdateIssues": len(set(open_review_update_issue_numbers)),
            "unpromotedPending": len(
                _queue_paths_unpromoted(queue_paths=pending_paths, queue_issue_numbers=queue_issue_numbers)
            ),
            "pendingDevelopment": len(dev_pending),
            "pendingReview": len(review_pending),
            "pendingCapabilityUpdates": len(cap_pending),
            "pendingExcluded": len(excluded_pending),
            "pendingDevelopmentWithoutPr": len(dev_promoted_no_pr),
            "pendingDevelopmentWithPr": len(dev_with_pr),
            "pendingDevelopmentReadyForReview": len(dev_ready_for_review),
            "pendingReviewWithoutPr": len(review_promoted_no_pr),
            "pendingReviewWithPr": len(review_with_pr),
            "pendingReviewReadyForReview": len(review_ready_for_review),
            "pendingCapabilityUpdatesWithoutPr": len(cap_promoted_no_pr),
            "pendingCapabilityUpdatesWithPr": len(cap_with_pr),
            "pendingCapabilityUpdatesReadyForReview": len(cap_ready_for_review),
            # Issue-driven capability update signals.
            "openCapabilityUpdateIssues": len(cap_issue_nums),
            "openCapabilityUpdateIssuesWithPr": (1 if cap_issue_with_pr else 0),
            "openCapabilityUpdateIssuesReadyForReview": (1 if cap_issue_ready_for_review else 0),
        },
        "debug": {
            "pendingQueueFilesSample": pending_paths[:20],
            "processedQueueFilesSample": processed_paths[:20],
            "completeQueueFilesSample": complete_paths[:20],
            "pendingExcludedPrefixes": list(_QUEUE_EXCLUDED_PREFIXES),
            "gapAnalysisIssueTitles": list(_GAP_ANALYSIS_TITLES),
            "issueTimelineLookups": debug_counters.get("issueTimelineLookups", 0),
            "pullRequestLookups": debug_counters.get("pullRequestLookups", 0),
        },
        "warnings": warnings,
        "focus": focus,
        "runningJob": None,
        "lastAction": None,
    }
