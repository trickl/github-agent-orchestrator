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


def _loop_status_for_repo(
    *, settings: ServerSettings, active_repo: str, ref: str
) -> dict[str, object]:
    from github_agent_orchestrator.server import dashboard_router

    mode = getattr(settings, "loop_mode", "build")
    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/pending",
        ref=ref,
    )
    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/processed",
        ref=ref,
    )
    complete_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/complete",
        ref=ref,
    )

    pending_count = len(pending_paths)
    processed_count = len(processed_paths)
    complete_count = len(complete_paths)

    # --- GitHub repo-derived signals (no local checkout/state) ---
    raw_issues = _list_open_issues_raw(settings, repository=active_repo)
    open_issue_titles: list[str] = []
    open_capability_issue_numbers: list[int] = []
    open_review_update_issue_numbers: list[int] = []
    open_review_consumption_issue_numbers: list[int] = []
    open_issue_titles_by_number: dict[int, str] = {}
    for it in raw_issues:
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if isinstance(title, str):
            open_issue_titles.append(title)
            if isinstance(num, int):
                open_issue_titles_by_number[num] = title
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_CAPABILITY):
            open_capability_issue_numbers.append(num)
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_REVIEW):
            open_review_update_issue_numbers.append(num)
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_REVIEW_CONSUMPTION):
            open_review_consumption_issue_numbers.append(num)

    gap_issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if isinstance(num, int) and isinstance(title, str) and _is_gap_analysis_issue_title(title):
            gap_issue_nums.append(num)

    has_open_gap_analysis_issue = bool(gap_issue_nums)

    raw_open_prs = _list_open_pull_requests_raw(settings, repository=active_repo, limit=100)
    open_pr_count = len(raw_open_prs)

    pending_files = [_queue_filename(p) for p in pending_paths]
    pending_by_category: dict[str, list[str]] = {}
    for filename in pending_files:
        pending_by_category.setdefault(_queue_category_for_filename(filename), []).append(filename)

    dev_pending = pending_by_category.get("development", [])
    review_pending = pending_by_category.get("review", [])
    cap_pending = pending_by_category.get("capability", [])
    excluded_pending = [
        f
        for f in pending_files
        if _queue_file_is_excluded_for_loop_mode(filename=f, loop_mode=mode)
    ]

    processed_files = [_queue_filename(p) for p in processed_paths]
    processed_by_category: dict[str, list[str]] = {}
    for filename in processed_files:
        processed_by_category.setdefault(_queue_category_for_filename(filename), []).append(
            filename
        )

    dev_processed = processed_by_category.get("development", [])
    review_processed = processed_by_category.get("review", [])
    cap_processed = processed_by_category.get("capability", [])

    # Associate queue files (pending + processed) -> GitHub issues by matching the file title
    # (first line) to open issue titles. Then associate issues -> PRs via issue timeline events.
    queue_issue_numbers: dict[str, int | None] = {}
    queue_display_titles: dict[str, str] = {}
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    pr_lookups = 0
    timeline_lookups = 0

    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]
    pr_cache: dict[int, dict[str, Any]] = {}
    pr_review_request_cache: dict[int, bool] = {}

    queue_paths_for_linkage = list(pending_paths) + list(processed_paths)
    for queue_path in queue_paths_for_linkage:
        content, _sha = _get_repo_text_file(
            settings,
            repository=active_repo,
            path=queue_path,
            ref=ref,
        )

        # Display title keeps original casing for UI; matching uses normalized title.
        display_title = ""
        for raw in content.splitlines():
            line = raw.strip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                line = line.lstrip().lstrip("#").strip()
            display_title = line.strip()
            break
        if display_title:
            queue_display_titles[queue_path] = display_title

        title_norm = _first_markdown_line_as_title(content)
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        queue_issue_numbers[queue_path] = issue_num

        if issue_num is None:
            continue

        if issue_num not in issue_to_open_prs:
            timeline = _list_issue_timeline_raw(
                settings, repository=active_repo, issue_number=issue_num
            )
            timeline_lookups += 1
            pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

            open_prs: list[dict[str, Any]] = []
            ready_prs: list[dict[str, Any]] = []
            for pr_num in sorted(pr_nums):
                pr_data = pr_cache.get(pr_num)
                if pr_data is None:
                    pr_data = _get_pull_request(settings, repository=active_repo, pr_number=pr_num)
                    pr_cache[pr_num] = pr_data
                    pr_lookups += 1

                if pr_data.get("state") != "open":
                    continue
                open_prs.append(pr_data)

                review_requested = _pull_request_has_review_request(pr_data)
                if not review_requested:
                    cached_rr = pr_review_request_cache.get(pr_num)
                    if cached_rr is None:
                        cached_rr = _pull_request_has_review_request_history(
                            settings,
                            repository=active_repo,
                            pr_number=pr_num,
                        )
                        pr_review_request_cache[pr_num] = cached_rr
                        timeline_lookups += 1
                    review_requested = cached_rr

                if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                    ready_prs.append(pr_data)

            issue_to_open_prs[issue_num] = open_prs
            issue_to_open_ready_prs[issue_num] = ready_prs

    # Capability update issues (Step E/F/G) are derived from labels, not queue files.
    cap_issue_nums = sorted(set(open_capability_issue_numbers))
    cap_issue_with_pr = False
    cap_issue_ready_for_review = False
    cap_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    cap_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in cap_issue_nums:
        if issue_num in issue_to_open_prs:
            cap_open_prs_existing = list(issue_to_open_prs.get(issue_num) or [])
            cap_ready_prs_existing = list(issue_to_open_ready_prs.get(issue_num) or [])
            cap_issue_to_open_prs[issue_num] = cap_open_prs_existing
            cap_issue_to_open_ready_prs[issue_num] = cap_ready_prs_existing
            cap_issue_with_pr = cap_issue_with_pr or bool(cap_open_prs_existing)
            cap_issue_ready_for_review = cap_issue_ready_for_review or bool(cap_ready_prs_existing)
            continue

        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        cap_open_prs_list: list[dict[str, Any]] = []
        cap_ready_prs_list: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            cap_issue_with_pr = True
            cap_open_prs_list.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                cap_issue_ready_for_review = True
                cap_ready_prs_list.append(pr_data)

        cap_issue_to_open_prs[issue_num] = cap_open_prs_list
        cap_issue_to_open_ready_prs[issue_num] = cap_ready_prs_list

    # Gap-analysis issues (Step A) are derived from titles, not queue artefacts.
    gap_issue_nums = sorted(set(gap_issue_nums))
    gap_issue_with_pr = False
    gap_issue_ready_for_review = False
    gap_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    gap_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in gap_issue_nums:
        if issue_num in issue_to_open_prs:
            gap_open_prs_existing = list(issue_to_open_prs.get(issue_num) or [])
            gap_ready_prs_existing = list(issue_to_open_ready_prs.get(issue_num) or [])
            gap_issue_to_open_prs[issue_num] = gap_open_prs_existing
            gap_issue_to_open_ready_prs[issue_num] = gap_ready_prs_existing
            gap_issue_with_pr = gap_issue_with_pr or bool(gap_open_prs_existing)
            gap_issue_ready_for_review = gap_issue_ready_for_review or bool(gap_ready_prs_existing)
            continue

        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        gap_open_prs_list: list[dict[str, Any]] = []
        gap_ready_prs_list: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            gap_issue_with_pr = True
            gap_open_prs_list.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                gap_issue_ready_for_review = True
                gap_ready_prs_list.append(pr_data)

        gap_issue_to_open_prs[issue_num] = gap_open_prs_list
        gap_issue_to_open_ready_prs[issue_num] = gap_ready_prs_list

    # Review-mode issues are derived from labels.
    review_intake_issue_nums = sorted(set(open_review_consumption_issue_numbers))
    review_update_issue_nums = sorted(set(open_review_update_issue_numbers))

    review_intake_with_pr = False
    review_intake_ready_for_review = False
    review_intake_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    review_intake_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in review_intake_issue_nums:
        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        intake_open_prs: list[dict[str, Any]] = []
        intake_ready_prs: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            review_intake_with_pr = True
            intake_open_prs.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                review_intake_ready_for_review = True
                intake_ready_prs.append(pr_data)

        review_intake_issue_to_open_prs[issue_num] = intake_open_prs
        review_intake_issue_to_open_ready_prs[issue_num] = intake_ready_prs

    review_update_with_pr = False
    review_update_ready_for_review = False
    review_update_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    review_update_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in review_update_issue_nums:
        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        upd_open_prs: list[dict[str, Any]] = []
        upd_ready_prs: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            review_update_with_pr = True
            upd_open_prs.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                review_update_ready_for_review = True
                upd_ready_prs.append(pr_data)

        review_update_issue_to_open_prs[issue_num] = upd_open_prs
        review_update_issue_to_open_ready_prs[issue_num] = upd_ready_prs

    dev_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(dev_pending)]
    review_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(review_pending)]
    cap_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(cap_pending)]
    dev_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(dev_processed)]
    review_processed_paths = [
        p for p in processed_paths if _queue_filename(p) in set(review_processed)
    ]
    cap_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(cap_processed)]

    dev_inflight_paths = dev_pending_paths + dev_processed_paths
    review_inflight_paths = review_pending_paths + review_processed_paths
    cap_inflight_paths = cap_pending_paths + cap_processed_paths

    def _has_associated_open_pr(queue_path: str) -> bool:
        issue_num = queue_issue_numbers.get(queue_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_prs.get(issue_num))

    def _has_associated_ready_pr(queue_path: str) -> bool:
        issue_num = queue_issue_numbers.get(queue_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_ready_prs.get(issue_num))

    dev_with_pr = [p for p in dev_inflight_paths if _has_associated_open_pr(p)]
    dev_ready_for_review = [p for p in dev_inflight_paths if _has_associated_ready_pr(p)]
    review_with_pr = [p for p in review_inflight_paths if _has_associated_open_pr(p)]
    review_ready_for_review = [p for p in review_inflight_paths if _has_associated_ready_pr(p)]

    cap_with_pr = [p for p in cap_inflight_paths if _has_associated_open_pr(p)]
    cap_ready_for_review = [p for p in cap_inflight_paths if _has_associated_ready_pr(p)]

    dev_unpromoted = [p for p in dev_pending_paths if queue_issue_numbers.get(p) is None]
    review_unpromoted = [p for p in review_pending_paths if queue_issue_numbers.get(p) is None]
    dev_promoted_no_pr = [
        p
        for p in dev_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]
    review_promoted_no_pr = [
        p
        for p in review_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]
    cap_unpromoted = [p for p in cap_pending_paths if queue_issue_numbers.get(p) is None]
    cap_promoted_no_pr = [
        p
        for p in cap_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]

    # --- Stage selection (priority is loop order) ---
    # Stages are stable 1a–3c; labels vary by loop mode.
    if mode == "review":
        # Review intake (Step 1)
        if review_intake_issue_nums:
            if review_intake_ready_for_review:
                stage = "1c"
                stage_label = "1c — Review intake PR ready for merge"
                active_step = 2
                stage_reason = "open review intake issue has an associated open PR ready for review"
            elif review_intake_with_pr:
                stage = "1b"
                stage_label = "1b — Review intake execution"
                active_step = 1
                stage_reason = "open review intake issue has an associated open PR"
            else:
                stage = "1a"
                stage_label = "1a — Review intake issue"
                active_step = 0
                stage_reason = "open review intake issue detected (no PR yet)"
        # Review actions update (Step 3)
        elif review_update_issue_nums:
            # We intentionally reuse the E/F/G step numbers for the update phase.
            if review_update_ready_for_review:
                stage = "3c"
                stage_label = "3c — Review actions PR ready for merge"
                active_step = 8
                stage_reason = "open review update issue has an associated open PR ready for review"
            elif review_update_with_pr:
                stage = "3b"
                stage_label = "3b — Review actions update execution"
                active_step = 7
                stage_reason = "open review update issue has an associated open PR"
            else:
                stage = "3a"
                stage_label = "3a — Review actions update issue"
                active_step = 6
                stage_reason = "open review update issue exists (no PR yet)"
        # Development (Step 2) from review queue artefacts
        elif review_pending or review_processed or dev_pending or dev_processed:
            work_unpromoted = review_unpromoted + dev_unpromoted
            work_ready = review_ready_for_review + dev_ready_for_review
            work_with_pr = review_with_pr + dev_with_pr

            if work_unpromoted:
                stage = "2a"
                stage_label = "2a — Development issue creation"
                active_step = 3
                stage_reason = "pending work queue file(s) exist without an associated open issue"
            elif work_ready:
                stage = "2c"
                stage_label = "2c — Development PR ready for merge"
                active_step = 5
                stage_reason = "work has an open PR with review requested and no conflicts"
            else:
                stage = "2b"
                stage_label = "2b — Development execution"
                active_step = 4
                if work_with_pr:
                    stage_reason = "pending work queue file(s) have an associated open PR"
                else:
                    stage_reason = (
                        "pending work queue file(s) have an associated open issue but no PR yet"
                    )
        elif processed_count > 0:
            stage = "2b"
            stage_label = "2b — Development execution"
            active_step = 4
            stage_reason = "processed queue artefacts exist"
        else:
            stage = "1a"
            stage_label = "1a — Review intake issue"
            active_step = 0
            stage_reason = "no pending/processed artefacts"

    # Build mode (existing semantics)
    elif has_open_gap_analysis_issue:
        if gap_issue_ready_for_review:
            stage = "1c"
            stage_label = "1c — Gap analysis PR ready for merge"
            active_step = 2
            stage_reason = "open gap analysis issue has an associated open PR ready for review"
        elif gap_issue_with_pr:
            stage = "1b"
            stage_label = "1b — Gap analysis execution"
            active_step = 1
            stage_reason = "open gap analysis issue has an associated open PR"
        else:
            stage = "1a"
            stage_label = "1a — Gap analysis issue"
            active_step = 0
            stage_reason = "open gap analysis issue detected (no PR yet)"
    elif cap_issue_nums:
        if cap_issue_ready_for_review:
            stage = "3c"
            stage_label = "3c — Capability PR ready for merge"
            active_step = 8
            stage_reason = (
                "open capability update issue exists and has an associated open PR ready for review"
            )
        elif cap_issue_with_pr:
            stage = "3b"
            stage_label = "3b — Capability update execution"
            active_step = 7
            stage_reason = "open capability update issue exists and has an associated open PR"
        else:
            stage = "3a"
            stage_label = "3a — Capability update issue"
            active_step = 6
            stage_reason = "open capability update issue exists (no PR yet)"
    elif dev_pending or dev_processed:
        if dev_unpromoted:
            stage = "2a"
            stage_label = "2a — Development issue creation"
            active_step = 3
            stage_reason = (
                "pending development queue file(s) exist without an associated open issue"
            )
        elif dev_ready_for_review:
            stage = "2c"
            stage_label = "2c — Development PR ready for merge"
            active_step = 5
            stage_reason = "development work has an open PR with review requested and no conflicts"
        else:
            stage = "2b"
            stage_label = "2b — Development execution"
            active_step = 4
            if dev_with_pr:
                stage_reason = "pending development queue file(s) have an associated open PR"
            else:
                stage_reason = (
                    "pending development queue file(s) have an associated open issue but no PR yet"
                )
    elif cap_pending or cap_processed:
        # Legacy path: capability update represented by queue artefacts.
        if cap_unpromoted:
            stage = "3a"
            stage_label = "3a — Capability update queued"
            active_step = 6
            stage_reason = (
                "pending capability update queue file(s) exist without an associated open issue"
            )
        elif cap_ready_for_review:
            stage = "3c"
            stage_label = "3c — Capability PR ready for merge"
            active_step = 8
            stage_reason = "pending capability update queue file(s) have an associated ready PR"
        else:
            stage = "3b"
            stage_label = "3b — Capability update in progress"
            active_step = 7
            stage_reason = "pending capability update queue file(s) have an associated open PR"
    elif processed_count > 0:
        stage = "2b"
        stage_label = "2b — Development execution"
        active_step = 4
        stage_reason = "processed queue artefacts exist"
    else:
        stage = "1a"
        stage_label = "1a — Gap analysis issue"
        active_step = 0
        stage_reason = "no pending/processed artefacts"

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
    if mode == "review":
        warnings.append(
            f"Review intake issues are detected by the '{LABEL_REVIEW_CONSUMPTION}' label (open issues)."
        )
        warnings.append(
            f"Review update issues are detected by the '{LABEL_UPDATE_REVIEW}' label (open issues)."
        )

    def _first_path(paths: list[str]) -> str | None:
        if not paths:
            return None
        return sorted(paths)[0]

    focus: dict[str, object] | None = None
    if mode == "review" and stage in {"1a", "1b", "1c"} and review_intake_issue_nums:
        issue_num = sorted(review_intake_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = review_intake_issue_to_open_prs.get(issue_num) or []
        ready_prs = review_intake_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        focus_pr_num: int | None = None
        focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                focus_pr_url = raw_pr_url

        focus = {
            "kind": "review",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": dashboard_router._make_github_issue_url(active_repo, issue_num),
            "pullNumber": focus_pr_num,
            "pullUrl": focus_pr_url,
        }
    elif mode == "review" and stage in {"3a", "3b", "3c"} and review_update_issue_nums:
        issue_num = sorted(review_update_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = review_update_issue_to_open_prs.get(issue_num) or []
        ready_prs = review_update_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        upd_focus_pr_num: int | None = None
        upd_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                upd_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                upd_focus_pr_url = raw_pr_url

        focus = {
            "kind": "reviewUpdate",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": dashboard_router._make_github_issue_url(active_repo, issue_num),
            "pullNumber": upd_focus_pr_num,
            "pullUrl": upd_focus_pr_url,
        }
    elif stage in {"1a", "1b", "1c"} and gap_issue_nums:
        issue_num = gap_issue_nums[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = gap_issue_to_open_prs.get(issue_num) or []
        ready_prs = gap_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        gap_focus_pr_num: int | None = None
        gap_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                gap_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                gap_focus_pr_url = raw_pr_url

        focus = {
            "kind": "gap",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": dashboard_router._make_github_issue_url(active_repo, issue_num),
            "pullNumber": gap_focus_pr_num,
            "pullUrl": gap_focus_pr_url,
        }
    elif stage in {"2a", "2b", "2c"}:
        # In review mode, Step 2 spans both review queue artefacts and development queue artefacts.
        if mode == "review":
            inflight_paths = review_inflight_paths + dev_inflight_paths
            unpromoted_paths = review_unpromoted + dev_unpromoted
            ready_paths = review_ready_for_review + dev_ready_for_review
            with_pr_paths = review_with_pr + dev_with_pr
        else:
            inflight_paths = dev_inflight_paths
            unpromoted_paths = dev_unpromoted
            ready_paths = dev_ready_for_review
            with_pr_paths = dev_with_pr

        if stage == "2a":
            focus_path = _first_path(unpromoted_paths)
        elif stage == "2c":
            focus_path = _first_path(ready_paths)
        else:
            # Prefer items that already have PRs, then fall back to any inflight item.
            focus_path = _first_path(with_pr_paths) or _first_path(inflight_paths)

        if focus_path:
            issue_num = queue_issue_numbers.get(focus_path)
            focus_pr_num: int | None = None
            focus_pr_url: str | None = None
            if isinstance(issue_num, int):
                prs = issue_to_open_prs.get(issue_num) or []
                ready_prs = issue_to_open_ready_prs.get(issue_num) or []
                selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)
                if isinstance(selected_pr, dict):
                    raw_pr_num = selected_pr.get("number")
                    if isinstance(raw_pr_num, int):
                        focus_pr_num = raw_pr_num
                    raw_pr_url = selected_pr.get("html_url")
                    if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                        focus_pr_url = raw_pr_url

            title = queue_display_titles.get(focus_path) or ""
            if isinstance(issue_num, int) and issue_num in open_issue_titles_by_number:
                # If we have a clean match, prefer the canonical issue title.
                title = open_issue_titles_by_number.get(issue_num) or title

            focus = {
                "kind": "development",
                "queuePath": focus_path,
                "queueId": _queue_filename(focus_path),
                "title": title,
                "issueNumber": issue_num,
                "issueUrl": (
                    dashboard_router._make_github_issue_url(active_repo, int(issue_num))
                    if isinstance(issue_num, int)
                    else None
                ),
                "pullNumber": focus_pr_num,
                "pullUrl": focus_pr_url,
            }
    elif stage in {"3a", "3b", "3c"} and cap_issue_nums:
        issue_num = sorted(cap_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        # Attempt to recover the original (merged) PR that triggered this capability-update issue.
        # This is more useful for operator context than the templated capability issue title.
        issue_body = ""
        issue_title_for_parse = title
        try:
            issue_data = _github_get_json(
                settings,
                url=_repo_api_url(settings, repository=active_repo, path=f"issues/{issue_num}"),
            )
            raw_body = issue_data.get("body")
            raw_title = issue_data.get("title")
            if isinstance(raw_body, str):
                issue_body = raw_body
            if isinstance(raw_title, str) and raw_title.strip():
                issue_title_for_parse = raw_title
        except HTTPException:
            # Best-effort only: lack of issue body shouldn't break loop display.
            issue_body = ""

        source_pr_number = _extract_source_pr_number_from_capability_issue(
            repository=active_repo,
            issue_title=issue_title_for_parse,
            issue_body=issue_body,
        )
        source_pr_title: str | None = None
        source_pr_url: str | None = None
        if isinstance(source_pr_number, int):
            try:
                source_pr = _get_pull_request(
                    settings,
                    repository=active_repo,
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
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        cap_focus_pr_num: int | None = None
        cap_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                cap_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                cap_focus_pr_url = raw_pr_url

        focus = {
            "kind": "capability",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": dashboard_router._make_github_issue_url(active_repo, issue_num),
            "pullNumber": cap_focus_pr_num,
            "pullUrl": cap_focus_pr_url,
            "sourceTitle": source_pr_title,
            "sourcePullNumber": source_pr_number,
            "sourcePullUrl": source_pr_url,
        }

    # Best-effort automation: if configured, auto-link the focused issue to a likely PR.
    # This addresses cases where Copilot opened a PR without adding `Fixes #<issue>`.
    if isinstance(focus, dict):
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

    # Best-effort automation: if configured, auto-nudge Copilot to resume after a rate limit stop.
    # This is intentionally scoped to the focused PR only to avoid scanning the entire repo.
    if settings.auto_resume_copilot_on_rate_limit and isinstance(focus, dict):
        focus_pull_number = focus.get("pullNumber")
        if isinstance(focus_pull_number, int) and focus_pull_number > 0:
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
                [p for p in pending_paths if queue_issue_numbers.get(p) is None]
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
            "issueTimelineLookups": timeline_lookups,
            "pullRequestLookups": pr_lookups,
        },
        "warnings": warnings,
        "focus": focus,
        "runningJob": None,
        "lastAction": None,
    }
