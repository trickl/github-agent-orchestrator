"""Local template loading.

The dashboard server is intended to run from a local checkout of this repository.
Issue templates used to drive Copilot tasks live in *this* repo under
`planning/issue_templates/`.

These templates are intentionally NOT loaded from the target GitHub repository.
The target repo is the work arena; templates are the orchestrator's behavior.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def _find_repo_root(start: Path | None = None) -> Path:
    """Best-effort locate the repository root directory.

    We walk upward looking for `pyproject.toml` (and prefer roots that also contain
    a `planning/` directory).

    Raises:
        HTTPException: if the repo root cannot be found.
    """

    start_path = (start or Path(__file__)).resolve()
    candidates = [start_path, *start_path.parents]

    best: Path | None = None
    for p in candidates:
        if not (p / "pyproject.toml").exists():
            continue
        best = p
        if (p / "planning").exists():
            return p

    if best is not None:
        return best

    raise HTTPException(
        status_code=500,
        detail=(
            "Unable to locate local repository root (expected pyproject.toml in parent directories). "
            f"Start={start_path}"
        ),
    )


def load_local_template_or_raise(*, relative_path: str) -> str:
    """Load a UTF-8 template file from the local repository.

    Args:
        relative_path: Path relative to repo root (e.g. "planning/issue_templates/gap-analysis.md").

    Raises:
        HTTPException: if the file does not exist or cannot be read.
    """

    rel = relative_path.lstrip("/")
    root = _find_repo_root()
    full = (root / rel).resolve()

    # Prevent path traversal escaping repo root.
    try:
        full.relative_to(root)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template path (escapes repo root): {relative_path}",
        ) from e

    if not full.exists() or not full.is_file():
        raise HTTPException(
            status_code=502,
            detail=(
                "Local template file not found. "
                f"Expected {relative_path} at {full}"
            ),
        )

    try:
        content = full.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to read local template file: {relative_path} ({full})",
        ) from e

    if not content.strip():
        raise HTTPException(
            status_code=502,
            detail=f"Local template file was empty: {relative_path} ({full})",
        )

    return content
