"""Thin async GitHub REST client wrapper."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx


class GitHubClient:
    """Minimal authenticated client for GitHub REST API operations."""

    def __init__(self, token: str, base_url: str = "https://api.github.com") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    async def request(
        self,
        method: str,
        path_or_url: str,
        *,
        expected_status: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Issue a request and return decoded JSON payload when present."""
        url = self._resolve_url(path_or_url)
        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)

        if expected_status and response.status_code not in expected_status:
            response.raise_for_status()
        elif not expected_status:
            response.raise_for_status()

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def request_bytes(self, method: str, path_or_url: str, **kwargs: Any) -> bytes:
        """Issue a request and return raw bytes payload."""
        url = self._resolve_url(path_or_url)
        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers, **kwargs)

        response.raise_for_status()
        return response.content
