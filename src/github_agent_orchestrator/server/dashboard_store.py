"""File-backed stores for the dashboard API.

These stores intentionally keep things simple and local-first:
- JSON files for rules and timeline
- markdown files for planning docs and issue queue artefacts

They are designed to be dependency-free and easy to evolve.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _safe_load_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    items: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            items.append(item)
    return items


def _save_json_list(path: Path, items: Sequence[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [m.model_dump(mode="json") for m in items]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class NotFound(Exception):
    message: str


class TimelineEventModel(BaseModel):
    id: str
    tsIso: str
    kind: str
    summary: str
    ruleId: str | None = None
    issueId: str | None = None
    issueTitle: str | None = None
    typePath: str | None = None
    links: list[dict[str, str]] | None = None
    details: str | None = None


class TimelineStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def list(self) -> list[TimelineEventModel]:
        raw = _safe_load_json_list(self._path)
        return [TimelineEventModel.model_validate(item) for item in raw]

    def append(self, event: TimelineEventModel) -> None:
        events = self.list()
        events.append(event)
        _save_json_list(self._path, events)

    def latest(self) -> TimelineEventModel | None:
        events = self.list()
        if not events:
            return None
        return max(events, key=lambda e: e.tsIso)


class GenerationRuleModel(BaseModel):
    id: str
    name: str
    category: str
    enabled: bool
    promptText: str
    targetFolder: str
    trigger: dict[str, object]
    lastRunIso: str | None = None
    nextEligibleIso: str | None = None
    editable: bool = True


class RuleStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def list(self) -> list[GenerationRuleModel]:
        raw = _safe_load_json_list(self._path)
        rules = [GenerationRuleModel.model_validate(item) for item in raw]
        # Stable ordering for UI.
        rules.sort(key=lambda r: r.name.lower())
        return rules

    def get(self, rule_id: str) -> GenerationRuleModel:
        for r in self.list():
            if r.id == rule_id:
                return r
        raise NotFound("Rule not found")

    def upsert(self, rule: GenerationRuleModel) -> GenerationRuleModel:
        rules = self.list()
        replaced = False
        for idx, existing in enumerate(rules):
            if existing.id == rule.id:
                rules[idx] = rule
                replaced = True
                break
        if not replaced:
            rules.append(rule)
        _save_json_list(self._path, rules)
        return rule

    def create(self, partial: dict[str, object]) -> GenerationRuleModel:
        rule_id = str(partial.get("id") or "").strip() or str(uuid.uuid4())
        created = GenerationRuleModel.model_validate({"id": rule_id, **partial})
        return self.upsert(created)

    def delete(self, rule_id: str) -> None:
        rules = [r for r in self.list() if r.id != rule_id]
        _save_json_list(self._path, rules)

    def touch_last_run(self, rule_id: str) -> None:
        rule = self.get(rule_id)
        updated = rule.model_copy(update={"lastRunIso": _utc_now_iso()})
        self.upsert(updated)


def read_markdown_doc(path: Path) -> tuple[str, str | None]:
    if not path.exists():
        return ("", None)
    content = path.read_text(encoding="utf-8")
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    return (content, ts)


def write_issue_queue_item(pending_dir: Path, *, prefix: str, title: str, body: str) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{prefix}-{stamp}.md"
    path = pending_dir / filename

    # Minimal markdown structure. The orchestrator can evolve parsing later.
    content = f"# {title}\n\n{body.strip()}\n"
    path.write_text(content, encoding="utf-8")
    return path
