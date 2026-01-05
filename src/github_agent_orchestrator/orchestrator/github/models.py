"""Data models for GitHub API interactions.

This module contains dataclass definitions used by the GitHubClient
to represent GitHub entities (issues, pull requests, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CreatedIssue:
    """Minimal issue metadata returned from GitHub."""

    repository: str
    number: int
    title: str
    created_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class IssueDetails:
    """Minimal issue metadata fetched from GitHub."""

    repository: str
    number: int
    title: str
    created_at: datetime
    status: str
    assignees: list[str]


@dataclass(frozen=True, slots=True)
class LinkedPullRequest:
    """Minimal pull request metadata linked to an issue."""

    number: int
    url: str
    title: str
    state: str
    is_draft: bool
    merged: bool
    merged_at: str | None
    closed_at: str | None
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class PullRequestDetails:
    """Minimal pull request metadata needed for review/merge automation."""

    number: int
    state: str
    draft: bool
    merged: bool

    mergeable: bool | None
    mergeable_state: str | None

    head_ref: str
    head_sha: str
    head_repo_full_name: str

    base_ref: str
    base_repo_full_name: str

    node_id: str | None = None


@dataclass(frozen=True, slots=True)
class PullRequestContent:
    """Pull request content used for post-merge reporting."""

    number: int
    title: str
    body: str
    state: str
    merged: bool
    merged_at: str | None
    html_url: str | None


@dataclass(frozen=True, slots=True)
class PullRequestDiscussionItem:
    """An item in a PR's discussion stream (comments/reviews/review comments)."""

    created_at: datetime
    kind: str
    author: str
    body: str
    url: str | None


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Result of a pull request merge operation."""

    merged: bool
    message: str
    sha: str | None = None


@dataclass(frozen=True, slots=True)
class PullRequestCreated:
    """Result of creating a pull request."""

    number: int
    url: str | None
