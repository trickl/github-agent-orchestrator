"""GitHub App authentication helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import httpx
import jwt

from backend.app.config import Settings
from backend.app.github.client import GitHubClient


def _resolve_url(base_url: str, path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return urljoin(f"{base_url.rstrip('/')}/", normalized.lstrip("/"))


def _normalized_private_key(pem_value: str) -> str:
    return pem_value.replace("\\n", "\n")


def _create_app_jwt(settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": settings.github_app_id,
    }
    return jwt.encode(
        payload,
        _normalized_private_key(settings.github_app_private_key),
        algorithm="RS256",
    )


async def _request_as_app(settings: Settings, method: str, path: str, **kwargs):
    token = _create_app_jwt(settings)
    headers = kwargs.pop("headers", {})
    headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            _resolve_url(settings.github_api_url, path),
            headers=headers,
            **kwargs,
        )
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


async def _installation_id_for_repo(settings: Settings, owner: str, repo: str) -> int:
    payload = await _request_as_app(settings, "GET", f"/repos/{owner}/{repo}/installation")
    installation_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(installation_id, int):
        raise RuntimeError(f"GitHub App installation not found for {owner}/{repo}")
    return installation_id


async def _default_installation_id(settings: Settings) -> int:
    if settings.github_app_installation_id is not None:
        return settings.github_app_installation_id
    payload = await _request_as_app(
        settings,
        "GET",
        "/app/installations",
        params={"per_page": 1},
    )
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("No GitHub App installations available")
    installation_id = payload[0].get("id") if isinstance(payload[0], dict) else None
    if not isinstance(installation_id, int):
        raise RuntimeError("Unable to resolve default GitHub App installation id")
    return installation_id


async def _installation_token(settings: Settings, installation_id: int) -> str:
    payload = await _request_as_app(
        settings,
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
    )
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("Failed to mint GitHub App installation token")
    return token


async def create_github_client(
    settings: Settings,
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> GitHubClient:
    """Create an authenticated GitHub API client using a GitHub App installation token."""

    if owner and repo:
        installation_id = await _installation_id_for_repo(settings, owner, repo)
    else:
        installation_id = await _default_installation_id(settings)

    token = await _installation_token(settings, installation_id)
    return GitHubClient(token=token, base_url=settings.github_api_url)
