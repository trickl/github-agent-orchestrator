"""Utility functions shared across orchestrator commands."""

from __future__ import annotations


def parse_labels(value: str | None) -> list[str] | None:
    """Parse comma-separated labels string into a list.

    Args:
        value: Comma-separated labels string, or None.

    Returns:
        List of labels, or None if input is None or empty.
    """
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    labels = [p for p in parts if p]
    return labels or None
