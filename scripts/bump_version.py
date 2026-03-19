"""Bump project patch version in repository metadata files.

This script updates:
- `pyproject.toml` (`[project].version`)
- `src/github_agent_orchestrator/__init__.py` (`__version__`)

Usage:
    python scripts/bump_version.py          # prints next patch version only
    python scripts/bump_version.py --write  # updates files and prints new version
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
INIT_PATH = ROOT / "src" / "github_agent_orchestrator" / "__init__.py"

PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
INIT_VERSION_RE = re.compile(r'^__version__\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
SEMVER_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


def _next_patch(version: str) -> str:
    match = SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"Unsupported version format '{version}'. Expected semantic x.y.z")
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch")) + 1
    return f"{major}.{minor}.{patch}"


def _extract_version(text: str, pattern: re.Pattern[str], file_name: str) -> str:
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Unable to find version in {file_name}")
    return str(match.group("version"))


def _replace_version(text: str, pattern: re.Pattern[str], new_version: str, file_name: str) -> str:
    replaced, count = pattern.subn(
        lambda m: m.group(0).replace(str(m.group("version")), new_version),
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Expected exactly one version assignment in {file_name}, found {count}")
    return replaced


def bump_version(*, write: bool) -> str:
    pyproject_text = PYPROJECT_PATH.read_text(encoding="utf-8")
    init_text = INIT_PATH.read_text(encoding="utf-8")

    pyproject_version = _extract_version(pyproject_text, PYPROJECT_VERSION_RE, str(PYPROJECT_PATH))
    init_version = _extract_version(init_text, INIT_VERSION_RE, str(INIT_PATH))

    if pyproject_version != init_version:
        raise ValueError(
            "Version mismatch between pyproject.toml and __init__.py: "
            f"{pyproject_version} != {init_version}"
        )

    new_version = _next_patch(pyproject_version)

    if write:
        PYPROJECT_PATH.write_text(
            _replace_version(pyproject_text, PYPROJECT_VERSION_RE, new_version, str(PYPROJECT_PATH)),
            encoding="utf-8",
        )
        INIT_PATH.write_text(
            _replace_version(init_text, INIT_VERSION_RE, new_version, str(INIT_PATH)),
            encoding="utf-8",
        )

    return new_version


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump patch version in project metadata")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write updated versions to files (default is dry-run)",
    )
    args = parser.parse_args()

    print(bump_version(write=bool(args.write)))


if __name__ == "__main__":
    main()
