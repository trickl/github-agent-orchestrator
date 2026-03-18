"""Runtime configuration loader for the GAO CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from gao.modes import Mode

CONFIG_FILENAME = ".orchestrator.yml"


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime config resolved from repository files."""

    mode: Mode = Mode.SEMI


def _as_mapping(raw: Any, *, path: Path) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    raise ValueError(f"{path.name} must contain a YAML mapping")


def _parse_mode(raw_mode: Any, *, path: Path) -> Mode:
    if raw_mode is None:
        return Mode.SEMI
    if not isinstance(raw_mode, str):
        raise ValueError(f"{path.name} 'mode' must be a string")

    normalized = raw_mode.strip().lower()
    try:
        return Mode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in Mode)
        raise ValueError(f"{path.name} mode must be one of: {allowed}") from exc


def load_runtime_config(repo_root: Path) -> RuntimeConfig:
    """Load runtime config from ``.orchestrator.yml`` in ``repo_root``.

    If the config file is missing, defaults to ``mode: semi``.
    """

    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        return RuntimeConfig(mode=Mode.SEMI)

    raw_text = config_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text)
    data = _as_mapping(loaded, path=config_path)
    mode = _parse_mode(data.get("mode"), path=config_path)
    return RuntimeConfig(mode=mode)
