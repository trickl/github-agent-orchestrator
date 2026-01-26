"""Helpers for managing .env files used by the CLI bootstrap flow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_ENV_ASSIGN_RE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)?(?P<key>[A-Z0-9_]+)\s*=.*$")


def read_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def upsert_env_vars(
    *,
    path: Path,
    updates: dict[str, str],
    overwrite: bool = False,
    header: Iterable[str] | None = None,
) -> dict[str, str]:
    """Insert or update key/value pairs in an env file.

    Args:
        path: Path to the .env file.
        updates: Mapping of env var names to values.
        overwrite: If False, existing values are preserved.
        header: Optional header lines to prepend when creating a new file.

    Returns:
        Mapping of keys that were written to their final value.
    """

    normalized = {k.strip(): v for k, v in updates.items() if k.strip()}
    if not normalized:
        return {}

    lines = read_env_lines(path)
    if not lines and header:
        lines = list(header)

    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        match = _ENV_ASSIGN_RE.match(line)
        if not match:
            output.append(line)
            continue
        key = match.group("key")
        if key not in normalized:
            output.append(line)
            continue
        seen.add(key)
        if overwrite or not _line_has_value(line):
            output.append(f"{key}={normalized[key]}")
        else:
            output.append(line)

    for key, value in normalized.items():
        if key in seen:
            continue
        output.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")

    return {key: normalized[key] for key in normalized}


def _line_has_value(line: str) -> bool:
    match = _ENV_ASSIGN_RE.match(line)
    if not match:
        return False
    key = match.group("key")
    prefix = match.group("prefix") or ""
    rendered = line.strip()
    if rendered.startswith(prefix + key + "="):
        return True
    return False
