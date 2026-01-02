"""GitHub API client wrapper for Phase 1A.

This intentionally wraps PyGithub to keep GitHub calls out of CLI code and make tests easy.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from github import Auth, Github
from github.Repository import Repository

logger = logging.getLogger(__name__)


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

    # Optional GitHub node ID.
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
    merged: bool
    message: str
    sha: str | None = None


@dataclass(frozen=True, slots=True)
class PullRequestCreated:
    number: int
    url: str | None


class GitHubClient:
    """Small wrapper around PyGithub for the operations we need in Phase 1A."""

    def __init__(
        self,
        *,
        token: str,
        repository: str,
        base_url: str = "https://api.github.com",
        repo: Repository | None = None,
        github_api: Github | None = None,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        if not repository:
            raise ValueError("GitHub repository is required")

        self._token = token
        self._repository_name = repository
        self._rest_base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "github-agent-orchestrator",
            }
        )

        if repo is not None:
            self._repo = repo
            self._github = None
            logger.debug("Using injected Repository instance")
            return

        auth = Auth.Token(token)
        self._github = github_api or Github(auth=auth, base_url=base_url)

        self._repo = self._github.get_repo(repository)
        logger.info(
            "Authenticated with GitHub and connected to repository", extra={"repo": repository}
        )

    @property
    def repository(self) -> str:
        """Return the configured repository name ("owner/repo")."""

        return self._repository_name

    def _issues_url(self, *, issue_number: int, suffix: str = "") -> str:
        if issue_number <= 0:
            raise ValueError("issue_number must be a positive integer")
        if suffix and not suffix.startswith("/"):
            suffix = "/" + suffix
        return f"{self._rest_base_url}/repos/{self._repository_name}/issues/{issue_number}{suffix}"

    def _pulls_url(self, *, pull_number: int, suffix: str = "") -> str:
        if pull_number <= 0:
            raise ValueError("pull_number must be a positive integer")
        if suffix and not suffix.startswith("/"):
            suffix = "/" + suffix
        return f"{self._rest_base_url}/repos/{self._repository_name}/pulls/{pull_number}{suffix}"

    def _repo_url(self, *, repository: str, path: str) -> str:
        repo = repository.strip().strip("/")
        clean_path = path.lstrip("/")
        if clean_path:
            return f"{self._rest_base_url}/repos/{repo}/{clean_path}"
        return f"{self._rest_base_url}/repos/{repo}"

    def _graphql_url(self) -> str:
        """Return the GitHub GraphQL endpoint for the configured REST base URL.

        GitHub.com uses: https://api.github.com/graphql
        GitHub Enterprise Server often uses REST at /api/v3 and GraphQL at /api/graphql.

        Note: There is no REST endpoint to convert draft PRs to ready-for-review.
        See: https://github.com/orgs/community/discussions/70061
        """

        base = self._rest_base_url.rstrip("/")
        if base.endswith("/api/v3"):
            return base[: -len("/api/v3")] + "/api/graphql"
        return f"{base}/graphql"

    def _graphql_post(
        self,
        *,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._graphql_url()
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data: Any = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected GraphQL response")
        return data

    def get_repository_default_branch(self, *, repository: str | None = None) -> str:
        repo = (repository or self._repository_name).strip()
        url = self._repo_url(repository=repo, path="")
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        default_branch = data.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch.strip():
            return "main"
        return default_branch

    def get_branch_head_sha(self, *, branch: str, repository: str | None = None) -> str:
        repo = (repository or self._repository_name).strip()
        if not branch.strip():
            raise ValueError("branch is required")
        url = self._repo_url(repository=repo, path=f"git/ref/heads/{branch}")
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        obj = data.get("object")
        if not isinstance(obj, dict):
            raise ValueError("Unexpected ref response: missing object")
        sha = obj.get("sha")
        if not isinstance(sha, str) or not sha.strip():
            raise ValueError("Unexpected ref response: missing sha")
        return sha

    def create_branch(
        self,
        *,
        branch: str,
        base_sha: str,
        repository: str | None = None,
    ) -> None:
        repo = (repository or self._repository_name).strip()
        if not branch.strip():
            raise ValueError("branch is required")
        if not base_sha.strip():
            raise ValueError("base_sha is required")

        url = self._repo_url(repository=repo, path="git/refs")
        payload = {"ref": f"refs/heads/{branch}", "sha": base_sha}
        resp = self._session.post(url, json=payload, timeout=30)
        if resp.status_code == 422:
            # Branch likely already exists.
            return
        resp.raise_for_status()

    def get_text_file_from_repo(
        self,
        *,
        path: str,
        ref: str = "",
        repository: str | None = None,
    ) -> tuple[str, str]:
        """Return (text_content, sha) for a file in a repo at a ref.

        Raises:
            FileNotFoundError if not present.
        """

        repo = (repository or self._repository_name).strip()
        norm = path.lstrip("/")
        url = self._repo_url(repository=repo, path=f"contents/{norm}")
        params: dict[str, str] = {}
        if ref.strip():
            params["ref"] = ref

        resp = self._session.get(url, params=params or None, timeout=30)
        if resp.status_code == 404:
            raise FileNotFoundError(f"File not found: {path}")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        file_sha = data.get("sha")
        if not isinstance(file_sha, str) or not file_sha.strip():
            raise ValueError("Unexpected contents response: missing sha")

        encoding = data.get("encoding")
        content = data.get("content")
        if encoding == "base64" and isinstance(content, str):
            raw = base64.b64decode(content.encode("utf-8"))
            text = raw.decode("utf-8")
            return text, file_sha

        # Fallback: treat as plain string when possible.
        if isinstance(content, str):
            return content, file_sha
        raise ValueError("Unexpected contents response: missing content")

    def upsert_text_file_in_repo(
        self,
        *,
        path: str,
        content: str,
        branch: str,
        message: str,
        sha: str | None = None,
        repository: str | None = None,
    ) -> str:
        """Create or update a text file via the contents API.

        Returns:
            New file sha.
        """

        repo = (repository or self._repository_name).strip()
        norm = path.lstrip("/")
        url = self._repo_url(repository=repo, path=f"contents/{norm}")
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha is not None and sha.strip():
            payload["sha"] = sha

        resp = self._session.put(url, json=payload, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        content_info = data.get("content")
        if isinstance(content_info, dict):
            new_sha = content_info.get("sha")
            if isinstance(new_sha, str) and new_sha.strip():
                return new_sha
        raise ValueError("Unexpected contents upsert response: missing content sha")

    def delete_file_in_repo(
        self,
        *,
        path: str,
        sha: str,
        branch: str,
        message: str,
        repository: str | None = None,
    ) -> None:
        repo = (repository or self._repository_name).strip()
        norm = path.lstrip("/")
        url = self._repo_url(repository=repo, path=f"contents/{norm}")
        payload: dict[str, Any] = {"message": message, "sha": sha, "branch": branch}
        resp = self._session.delete(url, json=payload, timeout=30)
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        repository: str | None = None,
    ) -> PullRequestCreated:
        repo = (repository or self._repository_name).strip()
        url = self._repo_url(repository=repo, path="pulls")
        payload = {"title": title, "body": body, "head": head, "base": base}
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        number = data.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("Unexpected create PR response: missing number")
        html_url = data.get("html_url")
        if not isinstance(html_url, str) or not html_url.strip():
            html_url = None
        return PullRequestCreated(number=number, url=html_url)

    def _search_url(self, *, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._rest_base_url}/{path}"

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid datetime value")
        # GitHub commonly returns timestamps like "2025-01-01T00:00:00Z".
        iso = value.replace("Z", "+00:00")
        return datetime.fromisoformat(iso)

    def _get_paginated_json_list(self, url: str) -> list[dict[str, Any]]:
        """Fetch a REST endpoint that returns a JSON list, following basic pagination.

        Notes:
            We keep pagination intentionally simple for Phase 1/1A: fetch up to 10 pages of
            100 items each.
        """

        items: list[dict[str, Any]] = []
        per_page = 100
        for page in range(1, 11):
            resp = self._session.get(
                url,
                params={"per_page": per_page, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                break

            page_items: list[dict[str, Any]] = [p for p in payload if isinstance(p, dict)]
            items.extend(page_items)

            if len(payload) < per_page:
                break
        return items

    @staticmethod
    def _safe_login(value: object) -> str:
        if isinstance(value, dict):
            login = value.get("login")
            if isinstance(login, str) and login.strip():
                return login
        return "unknown"

    def get_pull_request_content(self, *, pull_number: int) -> PullRequestContent:
        """Fetch PR title/body plus merge state from REST."""

        url = self._pulls_url(pull_number=pull_number)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        number = data.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("Invalid pull request response: missing number")

        title = data.get("title")
        if not isinstance(title, str):
            title = ""

        body = data.get("body")
        if not isinstance(body, str):
            body = ""

        state = data.get("state")
        if not isinstance(state, str):
            state = ""

        merged = bool(data.get("merged"))

        merged_at = data.get("merged_at")
        if not isinstance(merged_at, str) or not merged_at.strip():
            merged_at = None

        html_url = data.get("html_url")
        if not isinstance(html_url, str) or not html_url.strip():
            html_url = None

        return PullRequestContent(
            number=number,
            title=title,
            body=body,
            state=state,
            merged=merged,
            merged_at=merged_at,
            html_url=html_url,
        )

    def get_pull_request_discussion(self, *, pull_number: int) -> list[PullRequestDiscussionItem]:
        """Fetch PR discussion items and return them in chronological order.

        Includes:
        - Issue comments on the PR conversation
        - Reviews (approval / change requests), with their review body
        - Review comments (inline diff comments)
        """

        discussion: list[PullRequestDiscussionItem] = []

        issue_comments_url = self._repo_url(
            repository=self._repository_name, path=f"issues/{pull_number}/comments"
        )
        for item in self._get_paginated_json_list(issue_comments_url):
            created_at = item.get("created_at")
            try:
                created_dt = self._parse_datetime(created_at)
            except Exception:
                continue

            body = item.get("body")
            if not isinstance(body, str):
                body = ""

            url = item.get("html_url")
            if not isinstance(url, str) or not url.strip():
                url = None

            discussion.append(
                PullRequestDiscussionItem(
                    created_at=created_dt,
                    kind="ISSUE_COMMENT",
                    author=self._safe_login(item.get("user")),
                    body=body,
                    url=url,
                )
            )

        reviews_url = self._repo_url(
            repository=self._repository_name,
            path=f"pulls/{pull_number}/reviews",
        )
        for item in self._get_paginated_json_list(reviews_url):
            created_at = item.get("submitted_at") or item.get("created_at")
            try:
                created_dt = self._parse_datetime(created_at)
            except Exception:
                continue

            state = item.get("state")
            if not isinstance(state, str):
                state = ""

            body = item.get("body")
            if not isinstance(body, str):
                body = ""

            if not body.strip() and state.strip():
                body = f"Review state: {state.strip()}"

            url = item.get("html_url")
            if not isinstance(url, str) or not url.strip():
                url = None

            discussion.append(
                PullRequestDiscussionItem(
                    created_at=created_dt,
                    kind="REVIEW",
                    author=self._safe_login(item.get("user")),
                    body=body,
                    url=url,
                )
            )

        review_comments_url = self._repo_url(
            repository=self._repository_name, path=f"pulls/{pull_number}/comments"
        )
        for item in self._get_paginated_json_list(review_comments_url):
            created_at = item.get("created_at")
            try:
                created_dt = self._parse_datetime(created_at)
            except Exception:
                continue

            body = item.get("body")
            if not isinstance(body, str):
                body = ""

            path = item.get("path")
            if isinstance(path, str) and path.strip():
                line = item.get("line")
                if isinstance(line, int) and line > 0:
                    body = f"File: {path}:{line}\n\n{body}".strip()
                else:
                    body = f"File: {path}\n\n{body}".strip()

            url = item.get("html_url")
            if not isinstance(url, str) or not url.strip():
                url = None

            discussion.append(
                PullRequestDiscussionItem(
                    created_at=created_dt,
                    kind="REVIEW_COMMENT",
                    author=self._safe_login(item.get("user")),
                    body=body,
                    url=url,
                )
            )

        discussion.sort(key=lambda d: d.created_at)
        return discussion

    def _parse_assignees_from_issue_json(self, data: dict[str, Any]) -> list[str]:
        raw_assignees = data.get("assignees")
        if not isinstance(raw_assignees, list):
            return []
        logins: list[str] = []
        for assignee in raw_assignees:
            if isinstance(assignee, dict):
                login = assignee.get("login")
                if isinstance(login, str) and login.strip():
                    logins.append(login)
        return logins

    @staticmethod
    def _parse_pull_request_json(data: dict[str, Any]) -> PullRequestDetails:
        number = data.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("Invalid pull request response: missing number")

        node_id = data.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            node_id = None

        state = data.get("state")
        if not isinstance(state, str):
            state = ""

        draft = bool(data.get("draft"))
        merged = bool(data.get("merged"))

        mergeable = data.get("mergeable")
        if not isinstance(mergeable, bool):
            mergeable = None

        mergeable_state = data.get("mergeable_state")
        if not isinstance(mergeable_state, str):
            mergeable_state = None

        head = data.get("head")
        base = data.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            raise ValueError("Invalid pull request response: missing head/base")

        head_ref = head.get("ref")
        head_sha = head.get("sha")
        head_repo = head.get("repo")
        base_ref = base.get("ref")
        base_repo = base.get("repo")

        if not isinstance(head_ref, str) or not head_ref.strip():
            raise ValueError("Invalid pull request response: missing head.ref")
        if not isinstance(head_sha, str) or not head_sha.strip():
            raise ValueError("Invalid pull request response: missing head.sha")
        if not isinstance(base_ref, str) or not base_ref.strip():
            raise ValueError("Invalid pull request response: missing base.ref")
        if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
            raise ValueError("Invalid pull request response: missing repo info")

        head_repo_full_name = head_repo.get("full_name")
        base_repo_full_name = base_repo.get("full_name")
        if not isinstance(head_repo_full_name, str) or not head_repo_full_name.strip():
            raise ValueError("Invalid pull request response: missing head.repo.full_name")
        if not isinstance(base_repo_full_name, str) or not base_repo_full_name.strip():
            raise ValueError("Invalid pull request response: missing base.repo.full_name")

        return PullRequestDetails(
            number=number,
            node_id=node_id,
            state=state,
            draft=draft,
            merged=merged,
            mergeable=mergeable,
            mergeable_state=mergeable_state,
            head_ref=head_ref,
            head_sha=head_sha,
            head_repo_full_name=head_repo_full_name,
            base_ref=base_ref,
            base_repo_full_name=base_repo_full_name,
        )

    @staticmethod
    def _linked_pr_numbers_from_issue_timeline(timeline: Any) -> set[int]:
        if not isinstance(timeline, list):
            return set()

        def _extract_pr_number(ev: dict[str, Any]) -> int | None:
            # Common: cross-referenced event with nested source.issue.pull_request
            source = ev.get("source")
            if isinstance(source, dict):
                issue = source.get("issue")
                if isinstance(issue, dict) and "pull_request" in issue:
                    num = issue.get("number")
                    if isinstance(num, int):
                        return num

            # Connected events may include a "subject" that is a PR.
            subject = ev.get("subject")
            if isinstance(subject, dict) and "pull_request" in subject:
                num = subject.get("number")
                if isinstance(num, int):
                    return num

            return None

        out: set[int] = set()
        for raw in timeline:
            if not isinstance(raw, dict):
                continue
            event = raw.get("event")
            if event not in {"cross-referenced", "connected"}:
                continue
            num = _extract_pr_number(raw)
            if num is not None:
                out.add(num)
        return out

    @staticmethod
    def _parse_linked_pull_request_rest(data: Any) -> LinkedPullRequest | None:
        if not isinstance(data, dict):
            return None

        number = data.get("number")
        if not isinstance(number, int) or number <= 0:
            return None

        # Prefer the human URL; fall back to API URL only if necessary.
        url = data.get("html_url")
        if not isinstance(url, str) or not url.strip():
            url = data.get("url")
        if not isinstance(url, str) or not url.strip():
            return None

        title = data.get("title")
        if not isinstance(title, str):
            title = ""

        state = data.get("state")
        if not isinstance(state, str):
            state = ""

        is_draft = bool(data.get("draft"))
        merged = bool(data.get("merged"))

        merged_at = data.get("merged_at")
        closed_at = data.get("closed_at")
        updated_at = data.get("updated_at")

        return LinkedPullRequest(
            number=number,
            url=url,
            title=title,
            state=state,
            is_draft=is_draft,
            merged=merged,
            merged_at=merged_at if isinstance(merged_at, str) else None,
            closed_at=closed_at if isinstance(closed_at, str) else None,
            updated_at=updated_at if isinstance(updated_at, str) else None,
        )

    def get_linked_pull_requests(self, *, issue_number: int) -> list[LinkedPullRequest]:
        """Return pull requests linked to an issue.

        We include both:
        - PRs that are known to close the issue (via closing keywords)
        - PRs connected/cross-referenced in the issue timeline

        This is implemented via the REST issue timeline API.
        """

        timeline_url = self._issues_url(issue_number=issue_number, suffix="timeline")
        headers = dict(self._session.headers)
        accept = headers.get("Accept")
        if not isinstance(accept, str) or not accept.strip():
            accept = "application/vnd.github+json"
        headers["Accept"] = ", ".join([accept, "application/vnd.github.mockingbird-preview+json"])
        resp = self._session.get(
            timeline_url,
            headers=headers,
            params={"per_page": "100"},
            timeout=30,
        )
        resp.raise_for_status()
        timeline: Any = resp.json()

        pr_numbers = sorted(self._linked_pr_numbers_from_issue_timeline(timeline))
        linked: list[LinkedPullRequest] = []
        for pr_number in pr_numbers:
            pr_url = self._pulls_url(pull_number=pr_number)
            pr_resp = self._session.get(pr_url, timeout=30)
            if pr_resp.status_code == 404:
                continue
            pr_resp.raise_for_status()
            pr = self._parse_linked_pull_request_rest(pr_resp.json())
            if pr is not None:
                linked.append(pr)

        linked.sort(key=lambda p: p.number)
        logger.info(
            "Linked pull requests fetched",
            extra={
                "repo": self._repository_name,
                "issue_number": issue_number,
                "pull_request_numbers": [p.number for p in linked],
            },
        )
        return linked

    def create_issue(
        self,
        *,
        title: str,
        body: str | None,
        labels: list[str] | None,
    ) -> CreatedIssue:
        if not title.strip():
            raise ValueError("Issue title is required")

        normalized_labels = labels or []
        issue = self._repo.create_issue(title=title, body=body or "", labels=normalized_labels)

        return CreatedIssue(
            repository=self._repository_name,
            number=issue.number,
            title=issue.title,
            created_at=issue.created_at,
            status=getattr(issue, "state", "open"),
        )

    def get_issue(self, *, issue_number: int) -> IssueDetails:
        """Fetch an issue by number via REST."""

        url = self._issues_url(issue_number=issue_number)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        number = data.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("Invalid issue response: missing number")

        title = data.get("title")
        if not isinstance(title, str):
            title = ""

        state = data.get("state")
        if not isinstance(state, str):
            state = ""

        created_at = self._parse_datetime(data.get("created_at"))
        assignees = self._parse_assignees_from_issue_json(data)

        return IssueDetails(
            repository=self._repository_name,
            number=number,
            title=title,
            created_at=created_at,
            status=state,
            assignees=assignees,
        )

    def find_issue_number_by_body_marker(self, *, marker: str) -> int | None:
        """Search for an issue in this repo whose body contains a marker string."""

        if not marker.strip():
            raise ValueError("marker must be non-empty")

        query = f'repo:{self._repository_name} is:issue in:body "{marker}"'
        url = self._search_url(path="search/issues")
        resp = self._session.get(url, params={"q": query}, timeout=30)
        resp.raise_for_status()

        payload: dict[str, Any] = resp.json()
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None

        # Pick the lowest-number match for determinism.
        numbers: list[int] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            num = item.get("number")
            if isinstance(num, int) and num > 0:
                numbers.append(num)
        return min(numbers) if numbers else None

    def get_pull_request(self, *, pull_number: int) -> PullRequestDetails:
        url = self._pulls_url(pull_number=pull_number)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        pr = self._parse_pull_request_json(data)
        logger.info(
            "Pull request fetched",
            extra={
                "repo": self._repository_name,
                "pull_number": pr.number,
                "state": pr.state,
                "draft": pr.draft,
                "merged": pr.merged,
                "mergeable": pr.mergeable,
                "mergeable_state": pr.mergeable_state,
            },
        )
        return pr

    def mark_pull_request_ready_for_review(self, *, pull_number: int) -> PullRequestDetails:
        """Convert a draft PR to 'ready for review'.

        If the PR is already ready, GitHub may return a validation error; in that case we
        simply fetch and return the current PR state.
        """

        pr = self.get_pull_request(pull_number=pull_number)
        if not pr.draft:
            return pr

        if not isinstance(pr.node_id, str) or not pr.node_id.strip():
            raise ValueError("Pull request is draft but node_id is missing; cannot mark ready")

        # There is no REST API endpoint for this; GitHub requires GraphQL.
        # https://github.com/orgs/community/discussions/70061
        mutation = (
            "mutation($pullRequestId: ID!) {"
            "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
            "    pullRequest { id isDraft }"
            "  }"
            "}"
        )

        payload = self._graphql_post(query=mutation, variables={"pullRequestId": pr.node_id})

        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            messages: list[str] = []
            for err in errors:
                if isinstance(err, dict):
                    msg = err.get("message")
                    if isinstance(msg, str) and msg.strip():
                        messages.append(msg.strip())
            message = "; ".join(messages) if messages else str(errors)

            # If the PR is already ready, callers want the current state.
            if "not a draft" in message.lower() or "not draft" in message.lower():
                return self.get_pull_request(pull_number=pull_number)

            raise RuntimeError(
                f"markPullRequestReadyForReview failed for PR #{pull_number}: {message}"
            )

        # GraphQL mutation succeeded; refetch for full details and consistency.
        pr = self.get_pull_request(pull_number=pull_number)
        logger.info(
            "Pull request marked ready for review",
            extra={
                "repo": self._repository_name,
                "pull_number": pr.number,
                "draft": pr.draft,
                "graphql_url": self._graphql_url(),
            },
        )
        return pr

    def merge_pull_request(
        self,
        *,
        pull_number: int,
        merge_method: str = "squash",
        commit_title: str = "",
        commit_message: str = "",
    ) -> MergeResult:
        """Attempt to merge a pull request.

        Returns:
            A MergeResult indicating whether the merge occurred.

        Notes:
            GitHub will refuse merges if the PR isn't mergeable, isn't approved, or
            required checks haven't passed. In those cases we return merged=False with
            a message so callers can decide whether to retry.
        """

        url = self._pulls_url(pull_number=pull_number, suffix="merge")
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title.strip():
            payload["commit_title"] = commit_title
        if commit_message.strip():
            payload["commit_message"] = commit_message

        resp = self._session.put(url, json=payload, timeout=30)
        if resp.status_code in {405, 409, 422}:
            # Not mergeable yet / validation failure.
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {}
            message = resp_json.get("message") if isinstance(resp_json, dict) else None
            if not isinstance(message, str) or not message.strip():
                message = f"Merge refused (HTTP {resp.status_code})"
            logger.info(
                "Pull request merge refused",
                extra={
                    "repo": self._repository_name,
                    "pull_number": pull_number,
                    "merge_message": message,
                },
            )
            return MergeResult(merged=False, message=message)

        resp.raise_for_status()
        merged_json: dict[str, Any] = resp.json()
        merged = bool(merged_json.get("merged"))
        sha = merged_json.get("sha")
        if not isinstance(sha, str):
            sha = None
        message = merged_json.get("message")
        if not isinstance(message, str):
            message = "merged" if merged else "merge result unknown"

        logger.info(
            "Pull request merge attempted",
            extra={"repo": self._repository_name, "pull_number": pull_number, "merged": merged},
        )
        return MergeResult(merged=merged, message=message, sha=sha)

    def delete_pull_request_branch(self, *, pull_number: int) -> bool:
        """Delete the head branch for a PR (safe, same-repo only).

        Returns:
            True if deletion succeeded, False if skipped or deletion failed.
        """

        pr = self.get_pull_request(pull_number=pull_number)

        # Safety: only delete branches in the same repository.
        if pr.head_repo_full_name != self._repository_name:
            logger.info(
                "Skipping branch deletion (PR from fork)",
                extra={
                    "repo": self._repository_name,
                    "pull_number": pr.number,
                    "head_repo": pr.head_repo_full_name,
                },
            )
            return False

        # Extra safety: avoid common default branch names.
        if pr.head_ref in {"main", "master"}:
            logger.warning(
                "Skipping branch deletion (protected/default-like branch)",
                extra={
                    "repo": self._repository_name,
                    "pull_number": pr.number,
                    "head_ref": pr.head_ref,
                },
            )
            return False

        url = self._repo_url(
            repository=pr.head_repo_full_name,
            path=f"git/refs/heads/{pr.head_ref}",
        )
        resp = self._session.delete(url, timeout=30)
        if resp.status_code in {204, 404}:
            logger.info(
                "Deleted PR branch",
                extra={
                    "repo": self._repository_name,
                    "pull_number": pr.number,
                    "head_ref": pr.head_ref,
                },
            )
            return True
        logger.warning(
            "Failed to delete PR branch",
            extra={
                "repo": self._repository_name,
                "pull_number": pr.number,
                "head_ref": pr.head_ref,
                "status_code": resp.status_code,
            },
        )
        return False

    def assign_issue(self, *, issue_number: int, assignees: list[str]) -> list[str]:
        """Assign an issue to one or more GitHub users/bots.

        Returns:
            The assignee logins returned by GitHub after the assignment attempt.

        Notes:
            We use the REST API response to reflect actual assignees. This avoids false positives
            where the API accepts a request but the assignment does not persist.
        """

        normalized = [a.strip() for a in assignees if a.strip()]
        if not normalized:
            raise ValueError("At least one assignee is required")

        url = self._issues_url(issue_number=issue_number, suffix="assignees")
        resp = self._session.post(url, json={"assignees": normalized}, timeout=30)
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        returned_assignees = self._parse_assignees_from_issue_json(data)
        logger.info(
            "Issue assigned",
            extra={
                "repo": self._repository_name,
                "issue_number": issue_number,
                "requested_assignees": normalized,
                "returned_assignees": returned_assignees,
            },
        )
        return returned_assignees

    def assign_issue_with_agent_assignment(
        self,
        *,
        issue_number: int,
        assignees: list[str],
        agent_assignment: dict[str, str] | None,
    ) -> list[str]:
        """Assign an issue and attach optional Copilot agent assignment metadata.

        This corresponds to the public-preview Copilot coding agent assignment support, where
        the issue is assigned to a special Copilot bot and a structured `agent_assignment`
        payload can be provided.
        """

        normalized = [a.strip() for a in assignees if a.strip()]
        if not normalized:
            raise ValueError("At least one assignee is required")

        payload: dict[str, Any] = {"assignees": normalized}
        if agent_assignment:
            # Only include non-empty values to keep the request minimal.
            payload["agent_assignment"] = {k: v for k, v in agent_assignment.items() if v.strip()}

        url = self._issues_url(issue_number=issue_number, suffix="assignees")
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        returned_assignees = self._parse_assignees_from_issue_json(data)
        logger.info(
            "Issue assigned with agent metadata",
            extra={
                "repo": self._repository_name,
                "issue_number": issue_number,
                "requested_assignees": normalized,
                "returned_assignees": returned_assignees,
                "has_agent_assignment": bool(agent_assignment),
            },
        )
        return returned_assignees

    def get_issue_assignees(self, *, issue_number: int) -> list[str]:
        """Return current assignee logins for an issue."""

        url = self._issues_url(issue_number=issue_number)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return self._parse_assignees_from_issue_json(data)

    def remove_assignees(self, *, issue_number: int, assignees: list[str]) -> list[str]:
        """Remove one or more assignees from an issue.

        Returns:
            The assignee logins returned by GitHub after the removal attempt.
        """

        normalized = [a.strip() for a in assignees if a.strip()]
        if not normalized:
            raise ValueError("At least one assignee is required")

        url = self._issues_url(issue_number=issue_number, suffix="assignees")
        resp = self._session.delete(url, json={"assignees": normalized}, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        returned_assignees = self._parse_assignees_from_issue_json(data)
        logger.info(
            "Issue assignees removed",
            extra={
                "repo": self._repository_name,
                "issue_number": issue_number,
                "removed_assignees": normalized,
                "returned_assignees": returned_assignees,
            },
        )
        return returned_assignees

    def close(self) -> None:
        self._session.close()
        if self._github is not None:
            self._github.close()
