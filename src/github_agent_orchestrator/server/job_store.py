"""Simple persisted job tracking for server background tasks.

We persist to the same agent_state directory as issues so the UI can survive
restarts (best-effort).

This is intentionally minimal. If/when we need reliability and scale, this
should move to a real queue (RQ/Celery) or a DB.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    job_id: str
    issue_number: int
    status: str
    created_at: str
    updated_at: str

    completion: str | None = None
    pull_request_numbers: list[int] = Field(default_factory=list)
    error: str | None = None


def _utc_iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass
class JobStore:
    path: Path

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def _load_unlocked(self) -> list[JobRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []
        return [JobRecord.model_validate(item) for item in raw]

    def _save_unlocked(self, jobs: list[JobRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [j.model_dump(mode="json") for j in jobs]
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def list(self) -> list[JobRecord]:
        with self._lock:
            return self._load_unlocked()

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            for job in self._load_unlocked():
                if job.job_id == job_id:
                    return job
            return None

    def create(self, *, job_id: str, issue_number: int) -> JobRecord:
        with self._lock:
            jobs = self._load_unlocked()
            now = _utc_iso_now()
            record = JobRecord(
                job_id=job_id,
                issue_number=issue_number,
                status="queued",
                created_at=now,
                updated_at=now,
                completion=None,
                pull_request_numbers=[],
                error=None,
            )
            jobs.append(record)
            self._save_unlocked(jobs)
            return record

    def update(self, job_id: str, **updates: object) -> JobRecord:
        with self._lock:
            jobs = self._load_unlocked()
            for idx, job in enumerate(jobs):
                if job.job_id != job_id:
                    continue
                now = _utc_iso_now()
                merged = job.model_copy(update={"updated_at": now, **updates})
                jobs[idx] = merged
                self._save_unlocked(jobs)
                return merged
            raise KeyError(job_id)
