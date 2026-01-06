"""Auto-link automation for connecting issues to PRs when GitHub signals are missing.

This module contains the logic for automatically adding closing keywords (e.g., "Fixes #N")
to PR descriptions when Copilot creates a PR but doesn't include the proper linkage, helping
to prevent the orchestrator loop from getting stuck.
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings

_ISSUE_CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:fixe[sd]?|close[sd]?|resolve[sd]?)\s+#(\d+)\b",
    re.IGNORECASE,
)


def _debug_append(debug: list[str] | None, message: str) -> None:
    if debug is not None:
        debug.append(message)


def _issue_is_mentioned_as_closing(body: str, issue_number: int) -> bool:
    if not isinstance(body, str) or not body.strip():
        return False
    for m in _ISSUE_CLOSING_KEYWORD_RE.finditer(body):
        try:
            if int(m.group(1)) == int(issue_number):
                return True
        except Exception:
            continue
    return False


def _issue_is_mentioned_as_closing_outside_code_blocks(body: str, issue_number: int) -> bool:
    # Import here to avoid circular dependency at module load time
    from github_agent_orchestrator.server import dashboard_router

    return _issue_is_mentioned_as_closing(
        dashboard_router._strip_fenced_code_blocks(body), issue_number
    )


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


def _focus_issue_number(focus: dict[str, object]) -> int | None:
    issue_number = focus.get("issueNumber")
    if isinstance(issue_number, int) and issue_number > 0:
        return issue_number
    return None


def _focus_has_pull_number(focus: dict[str, object]) -> bool:
    return focus.get("pullNumber") is not None


def _normalized_focus_title(focus: dict[str, object], normalize_title: Any) -> str:
    focus_title = focus.get("title")
    return normalize_title(focus_title) if isinstance(focus_title, str) else ""


def _pr_number(pr: dict[str, Any]) -> int | None:
    num = pr.get("number")
    if isinstance(num, int) and num > 0:
        return num
    return None


def _pr_looks_copilot_like(pr: dict[str, Any], copilot_logins: set[str]) -> tuple[bool, bool, bool]:
    user = pr.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    login_norm = login.strip().lower() if isinstance(login, str) and login.strip() else ""

    head = pr.get("head")
    head_ref = head.get("ref") if isinstance(head, dict) else None
    head_ref_norm = head_ref.strip() if isinstance(head_ref, str) and head_ref.strip() else ""

    looks_copilot_authored = bool(login_norm) and login_norm in copilot_logins
    looks_copilot_branched = head_ref_norm.lower().startswith("copilot/")
    return (looks_copilot_authored or looks_copilot_branched), looks_copilot_authored, looks_copilot_branched


def _pr_title(pr: dict[str, Any]) -> str | None:
    title = pr.get("title")
    if isinstance(title, str) and title.strip():
        return title
    return None


def _pr_title_matches_focus(
    *,
    pr_title: str,
    normalized_focus_title: str,
    normalize_title: Any,
) -> bool:
    if not normalized_focus_title:
        return False
    return normalize_title(pr_title) == normalized_focus_title


def _scan_pr_candidates(
    *,
    raw_open_prs: list[dict[str, Any]],
    normalized_focus_title: str,
    copilot_logins: set[str],
    normalize_title: Any,
    debug: list[str] | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    scanned = 0
    skipped_not_copilot_like = 0
    skipped_missing_title = 0
    title_matched = 0
    accepted_via_author = 0
    accepted_via_branch = 0

    for pr in raw_open_prs:
        if not isinstance(pr, dict):
            continue

        if _pr_number(pr) is None:
            continue

        scanned += 1
        looks_like, via_author, via_branch = _pr_looks_copilot_like(pr, copilot_logins)
        if not looks_like:
            skipped_not_copilot_like += 1
            continue

        accepted_via_author += 1 if via_author else 0
        accepted_via_branch += 1 if via_branch else 0

        title = _pr_title(pr)
        if title is None:
            skipped_missing_title += 1
            continue

        if _pr_title_matches_focus(
            pr_title=title,
            normalized_focus_title=normalized_focus_title,
            normalize_title=normalize_title,
        ):
            title_matched += 1
            candidates.append(pr)

    _debug_append(debug, f"Open PRs observed: {len(raw_open_prs)}")
    _debug_append(debug, f"Copilot login candidates: {sorted(copilot_logins)}")
    _debug_append(
        debug,
        "PR scan summary: "
        f"scanned={scanned}, skipped_not_copilot_like={skipped_not_copilot_like}, "
        f"accepted_via_author={accepted_via_author}, accepted_via_branch={accepted_via_branch}, "
        f"skipped_missing_title={skipped_missing_title}, title_matched={title_matched}.",
    )
    return candidates


def _single_open_pr_fallback_candidate(
    *,
    raw_open_prs: list[dict[str, Any]],
    copilot_logins: set[str],
) -> dict[str, Any] | None:
    if len(raw_open_prs) != 1 or not isinstance(raw_open_prs[0], dict):
        return None
    pr = raw_open_prs[0]
    looks_like, _via_author, _via_branch = _pr_looks_copilot_like(pr, copilot_logins)
    return pr if looks_like else None


def _auto_link_notice_comment_exists(comments: list[object], is_notice: Any) -> bool:
    for it in comments:
        if not isinstance(it, dict):
            continue
        body = it.get("body")
        if isinstance(body, str) and is_notice(body):
            return True
    return False


def maybe_auto_link_focused_issue_to_pr(
    *,
    settings: ServerSettings,
    repository: str,
    focus: dict[str, object],
    raw_open_prs: list[dict[str, Any]],
    debug: list[str] | None = None,
) -> str | None:
    """Best-effort: link the focused issue to a likely PR when GitHub signals are missing.

    This addresses cases where Copilot created a PR but didn't include `Fixes #<issue>` in the PR
    body, so the issue has no PR cross-reference and the loop appears "stuck" in stage 2b.

    Safety properties:
      - opt-in via settings.auto_link_focused_issue_pr
      - only runs when focus has an issueNumber but no pullNumber
      - only acts when a single high-confidence PR candidate can be identified
      - idempotent: does nothing if PR body already contains a closing keyword for the issue
    """
    # Import here to avoid circular dependency at module load time
    from github_agent_orchestrator.server import dashboard_router

    if not getattr(settings, "auto_link_focused_issue_pr", False):
        _debug_append(debug, "Auto-link disabled (ORCHESTRATOR_AUTO_LINK_FOCUSED_ISSUE_PR is false).")
        return None
    if not settings.github_token.strip():
        _debug_append(debug, "No GitHub token configured (ORCHESTRATOR_GITHUB_TOKEN is empty).")
        return None

    issue_number = _focus_issue_number(focus)
    if issue_number is None:
        _debug_append(debug, "Focus has no valid issueNumber; nothing to link.")
        return None
    if _focus_has_pull_number(focus):
        _debug_append(debug, "Focus already has a pullNumber; auto-link not applicable.")
        return None

    normalized_focus_title = _normalized_focus_title(focus, dashboard_router._normalize_issue_title)
    copilot_logins = _copilot_login_candidates(settings)
    candidates = _scan_pr_candidates(
        raw_open_prs=raw_open_prs,
        normalized_focus_title=normalized_focus_title,
        copilot_logins=copilot_logins,
        normalize_title=dashboard_router._normalize_issue_title,
        debug=debug,
    )

    # If we didn't get an exact title match, fall back to a very conservative heuristic:
    # only one open PR total AND it appears Copilot-authored.
    fallback = _single_open_pr_fallback_candidate(raw_open_prs=raw_open_prs, copilot_logins=copilot_logins)
    if not candidates and fallback is not None:
        _debug_append(debug, "No exact title match; using single-open-PR fallback.")
        candidates = [fallback]

    if len(candidates) != 1:
        _debug_append(debug, f"Candidate count is {len(candidates)} (expected 1); not linking.")
        return None

    pr_num = _pr_number(candidates[0])
    if pr_num is None:
        _debug_append(debug, "Candidate PR had no valid number; not linking.")
        return None

    pr_data = dashboard_router._get_pull_request(settings, repository=repository, pr_number=pr_num)
    pr_body = pr_data.get("body")
    if not isinstance(pr_body, str):
        pr_body = ""

    if _issue_is_mentioned_as_closing_outside_code_blocks(pr_body, issue_number):
        _debug_append(
            debug,
            f"PR #{pr_num} body already contains a closing keyword for issue #{issue_number}; no-op.",
        )
        return None

    # Put the closing keyword at the top-level of the PR body to avoid being swallowed by
    # unclosed Markdown fences (which would make GitHub ignore the keyword).
    new_body = (
        f"Fixes #{issue_number}\n\n<!-- {dashboard_router._AUTO_LINK_NOTICE_MARKER} -->\n\n"
        + pr_body.lstrip()
    )
    dashboard_router._github_patch_json(
        settings,
        url=dashboard_router._repo_api_url(settings, repository=repository, path=f"pulls/{pr_num}"),
        payload={"body": new_body},
    )

    # Add an explicit PR comment for transparency. (Note: comments don't create closing linkage,
    # but they do provide an audit trail for the intervention.)
    with suppress(HTTPException):
        comments = dashboard_router._list_issue_comments_raw(
            settings, repository=repository, issue_number=pr_num
        )
        if not _auto_link_notice_comment_exists(
            comments,
            dashboard_router._comment_body_is_auto_link_notice,
        ):
            notice = (
                f"<!-- {dashboard_router._AUTO_LINK_NOTICE_MARKER} -->\n"
                f"Orchestrator auto-linked this PR to issue #{issue_number} by adding "
                f"`Fixes #{issue_number}` to the PR description."
            )
            dashboard_router._github_post_json(
                settings,
                url=dashboard_router._repo_api_url(
                    settings, repository=repository, path=f"issues/{pr_num}/comments"
                ),
                payload={"body": notice},
            )

    _debug_append(debug, f"Patched PR #{pr_num} body with 'Fixes #{issue_number}' (prepended).")
    return (
        f"Auto-linked PR #{pr_num} to issue #{issue_number} by prepending 'Fixes #{issue_number}' "
        "to the PR body."
    )
