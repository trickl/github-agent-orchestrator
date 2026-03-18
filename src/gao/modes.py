"""Execution modes for the GAO runtime."""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    """Supported orchestrator execution modes."""

    MANUAL = "manual"
    SEMI = "semi"
    AUTO = "auto"


def should_auto_approve(mode: Mode) -> bool:
    """Return whether PRs should be auto-approved for the selected mode."""

    return mode == Mode.AUTO
