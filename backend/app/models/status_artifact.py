"""Typed schema for workflow `status.json` artifact payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StatusArtifact(BaseModel):
    """Normalized status artifact model used by the status endpoint."""

    stage: str | None = None
    active_issue_ids: list[int] = Field(default_factory=list)
    active_pr_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    def as_response_payload(self) -> dict[str, Any]:
        """Return model data in API-friendly shape while preserving extra keys."""
        return self.model_dump()
