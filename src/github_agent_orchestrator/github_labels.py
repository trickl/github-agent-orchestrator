"""Shared GitHub label conventions.

These labels are intended to be created and applied consistently across all issues
created by the orchestrator and dashboard.

We keep these as stable, human-readable names (not machine IDs) so that:
- repos can be bootstrapped idempotently (create if missing)
- users can filter and report easily
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LabelSpec:
    name: str
    color: str
    description: str


LABEL_GAP_ANALYSIS = "Gap Analysis"
LABEL_DEVELOPMENT = "Development"
LABEL_UPDATE_CAPABILITY = "Update Capability"


FIXED_LABEL_SPECS: tuple[LabelSpec, ...] = (
    LabelSpec(
        name=LABEL_GAP_ANALYSIS,
        color="1d76db",
        description="Orchestrator loop: gap analysis",
    ),
    LabelSpec(
        name=LABEL_DEVELOPMENT,
        color="0e8a16",
        description="Orchestrator loop: development work from issue queue",
    ),
    LabelSpec(
        name=LABEL_UPDATE_CAPABILITY,
        color="fbca04",
        description="Orchestrator loop: update system capabilities",
    ),
)


def fixed_label_spec_by_name(name: str) -> LabelSpec | None:
    normalized = name.strip()
    for spec in FIXED_LABEL_SPECS:
        if spec.name == normalized:
            return spec
    return None
