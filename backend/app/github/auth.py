"""PAT-based GitHub authentication helpers."""

from __future__ import annotations

from backend.app.config import Settings
from backend.app.github.client import GitHubClient


async def create_github_client(settings: Settings) -> GitHubClient:
    """Create an authenticated GitHub API client using a PAT."""
    return GitHubClient(token=settings.github_token, base_url=settings.github_api_url)
