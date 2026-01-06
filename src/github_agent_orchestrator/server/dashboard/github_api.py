"""GitHub REST/GraphQL plumbing used by the dashboard server.

This module is intentionally low-level: URL construction, headers, and HTTP request helpers.

Important refactor invariant:
- Functions are moved from `server.dashboard_router` verbatim first.
- Call sites are updated to import these functions without behavior changes.
"""

from __future__ import annotations

from typing import Any

import requests
from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings


TOKEN_ACCESS_HINT = (
    "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
    "has access to the repository."
)
ERR_UNEXPECTED_GITHUB_API_RESPONSE = "Unexpected GitHub API response"
ERR_UNEXPECTED_GITHUB_GRAPHQL_RESPONSE = "Unexpected GitHub GraphQL response"


def _github_headers(settings: ServerSettings) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-agent-orchestrator",
    }
    if settings.github_token.strip():
        headers["Authorization"] = f"Bearer {settings.github_token.strip()}"
    return headers


def _repo_api_url(settings: ServerSettings, *, repository: str, path: str) -> str:
    base = settings.github_base_url.rstrip("/")
    repo = repository.strip().strip("/")
    clean_path = path.lstrip("/")
    if clean_path:
        return f"{base}/repos/{repo}/{clean_path}"
    return f"{base}/repos/{repo}"


def _graphql_api_url(settings: ServerSettings) -> str:
    """Return the GitHub GraphQL endpoint for the configured base URL.

    GitHub.com uses https://api.github.com/graphql.
    GitHub Enterprise Server typically uses https://<host>/api/graphql, while REST is /api/v3.
    """

    base = settings.github_base_url.rstrip("/")
    if base.endswith("/api/v3"):
        return base[: -len("/api/v3")] + "/api/graphql"
    return f"{base}/graphql"


def _github_graphql_post(
    settings: ServerSettings,
    *,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a GraphQL query/mutation to GitHub.

    GitHub GraphQL errors are returned in the JSON body under "errors" with HTTP 200.
    Callers should inspect the returned payload.
    """

    url = _graphql_api_url(settings)
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    resp = requests.post(
        url,
        headers=_github_headers(settings),
        json=payload,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        raise HTTPException(
            status_code=502,
            detail=f"GitHub GraphQL request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any
    try:
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_GRAPHQL_RESPONSE) from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_GRAPHQL_RESPONSE)
    return data


def _graphql_errors_as_message(payload: dict[str, Any]) -> str | None:
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None

    messages: list[str] = []
    for err in errors:
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                messages.append(msg.strip())

    if messages:
        # Keep the message concise for UI surfacing.
        return "; ".join(messages[:3])
    return str(errors)[:500]


def _github_get_json(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> dict[str, Any]:
    resp = requests.get(
        url,
        headers=_github_headers(settings),
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        elif status == 404:
            hint = (
                "Repository or path not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_API_RESPONSE)
    return data


def _github_post_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    resp = requests.post(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        elif status == 404:
            hint = (
                "Repository or endpoint not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_API_RESPONSE)
    return data


def _github_post_json_with_status(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    """POST JSON and return (status, body) without raising.

    This mirrors _github_put_json and is used when callers want to interpret
    specific GitHub error statuses for state transitions.
    """

    resp = requests.post(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body

    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _github_put_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    resp = requests.put(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        # Caller may handle specific statuses (e.g. 422 for missing sha).
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body

    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _github_patch_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    resp = requests.patch(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        elif status == 404:
            hint = (
                "Repository or endpoint not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_API_RESPONSE)
    return data


def _github_delete_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    resp = requests.delete(
        url,
        headers=_github_headers(settings),
        json=payload or None,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body
    if status == 204:
        return status, None
    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _github_get_list(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    resp = requests.get(
        url,
        headers=_github_headers(settings),
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        elif status == 404:
            hint = (
                "Repository or path not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_API_RESPONSE)
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def _github_get_list_with_headers(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resp = requests.get(
        url,
        headers=headers,
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = TOKEN_ACCESS_HINT
        elif status == 404:
            hint = (
                "Repository or endpoint not found. If the repo is private, GitHub may return 404 when "
                "the token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_API_RESPONSE)
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out
