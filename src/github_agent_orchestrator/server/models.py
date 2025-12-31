"""Pydantic models for the REST server."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiIssue(BaseModel):
    issue_number: int
    title: str
    created_at: str
    status: str
    assignees: list[str]

    linked_pull_requests: list[dict[str, object]] = Field(default_factory=list)
    pr_last_checked_at: str | None = None
    pr_completion: str | None = None


class MonitorRequest(BaseModel):
    poll_seconds: float = Field(default=10.0, gt=0)
    timeout_seconds: float = Field(default=1800.0, ge=0)
    require_pr: bool = True


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class MonitorJob(BaseModel):
    job_id: str
    issue_number: int
    status: JobStatus

    created_at: datetime
    updated_at: datetime

    completion: str | None = None
    pull_request_numbers: list[int] = Field(default_factory=list)

    error: str | None = None
