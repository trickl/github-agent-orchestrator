"""Pure text and datetime utilities for dashboard modules.

This module contains pure helper functions that perform text processing,
datetime operations, and simple data transformations. All functions here
are leaf utilities with no dependencies on FastAPI, GitHub API, or other
dashboard modules.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

_COPILOT_RATE_LIMIT_RESUME_COMMENT = "@copilot please can you attempt to resume this work now?"


_AUTO_LINK_NOTICE_MARKER = "orchestrator:auto-link-focused-issue"


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _dt_from_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _utc_now()


def _comment_body_is_copilot_resume_nudge(body: str) -> bool:
    return _COPILOT_RATE_LIMIT_RESUME_COMMENT.lower() in (body or "").lower()


def _comment_body_is_auto_link_notice(body: str) -> bool:
    return _AUTO_LINK_NOTICE_MARKER.lower() in (body or "").lower()


def _strip_fenced_code_blocks(markdown: str) -> str:
    """Remove fenced code blocks from Markdown.

    This is a best-effort Markdown-aware filter used for detecting issue closing keywords.
    We deliberately keep this simple and deterministic.
    """

    if not isinstance(markdown, str) or not markdown:
        return ""

    out_lines: list[str] = []
    in_fence = False
    fence_delim: str | None = None

    for raw in markdown.splitlines():
        line = raw.rstrip("\n")
        stripped = line.lstrip()

        # Toggle on lines that begin with a fence. Accept ``` and ~~~ fences.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            delim = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_delim = delim
                continue
            if fence_delim == delim:
                in_fence = False
                fence_delim = None
                continue

        if not in_fence:
            out_lines.append(line)

    return "\n".join(out_lines)


def _normalize_issue_title(title: str) -> str:
    """Normalize a title for matching.

    We intentionally keep this simple and deterministic.
    """

    t = title.strip()
    if t.lstrip().startswith("#"):
        t = t.lstrip().lstrip("#").strip()
    return " ".join(t.lower().split())


def _first_markdown_line_as_title(content: str) -> str:
    for raw in content.splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        return _normalize_issue_title(line)
    return ""


def _normalize_repo_path_candidate(value: str) -> str:
    s = (value or "").strip()
    # Strip common Markdown wrappers.
    if s.startswith("`") and s.endswith("`") and len(s) >= 2:
        s = s[1:-1].strip()
    # Strip markdown link [text](path)
    m = re.match(r"^\[[^\]]+\]\(([^)]+)\)\s*$", s)
    if m:
        s = (m.group(1) or "").strip()
    # Trim trailing punctuation.
    s = s.strip(" \t\r\n;,.")
    return s.replace("\\", "/")
