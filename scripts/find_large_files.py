#!/usr/bin/env python3
"""Find large files in the repository.

This script is meant to support refactoring work by identifying files that exceed a
line-count threshold (default: 500). It intentionally uses a simple line-based
metric (physical lines) so it's fast, deterministic, and language-agnostic.

By default it scans only Python files (".py") and skips common generated/vendor
directories.

Examples:
  - Scan default (Python only), show files > 500 lines:
      ./scripts/find_large_files.py

  - Scan Python + Markdown:
      ./scripts/find_large_files.py --ext .py --ext .md

  - Emit markdown table to stdout:
      ./scripts/find_large_files.py --format md

  - Write JSON output:
      ./scripts/find_large_files.py --format json --output large_files.json

"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class FileStat:
    path: str
    lines: int


DEFAULT_EXCLUDE_DIR_NAMES: set[str] = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    ".coverage",
    ".tox",
}


def _should_skip_dir(path: Path, exclude_dir_names: set[str]) -> bool:
    # Skip if any path component matches an excluded directory.
    # This keeps behavior predictable even if the repo is nested.
    return any(part in exclude_dir_names for part in path.parts)


def _iter_files(root: Path, exts: set[str], exclude_dir_names: set[str]) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if _should_skip_dir(p, exclude_dir_names):
            continue
        if exts and p.suffix not in exts:
            continue
        yield p


def _count_lines(path: Path) -> int:
    # Use binary reading + splitlines() to be robust to mixed/newline encodings.
    # Fall back to 'replace' for any decode errors.
    data = path.read_bytes()
    return len(data.decode("utf-8", errors="replace").splitlines())


def collect_file_stats(
    *,
    root: Path,
    exts: set[str],
    exclude_dir_names: set[str],
) -> list[FileStat]:
    stats: list[FileStat] = []
    for path in _iter_files(root, exts=exts, exclude_dir_names=exclude_dir_names):
        try:
            lines = _count_lines(path)
        except OSError:
            # Ignore unreadable files (permissions, transient FS issues).
            continue
        rel = path.relative_to(root).as_posix()
        stats.append(FileStat(path=rel, lines=lines))

    stats.sort(key=lambda s: s.lines, reverse=True)
    return stats


OutputFormat = Literal["text", "md", "json"]


def format_text(stats: Sequence[FileStat], *, threshold: int, top: int) -> str:
    over = [s for s in stats if s.lines >= threshold]
    lines: list[str] = []
    lines.append(f"Files >= {threshold} lines: {len(over)}")
    for s in over[:top]:
        lines.append(f"{s.lines:>6}  {s.path}")

    if len(over) > top:
        lines.append(f"... ({len(over) - top} more)")

    lines.append("")
    lines.append(f"Top {min(top, len(stats))} by line count:")
    for s in stats[:top]:
        lines.append(f"{s.lines:>6}  {s.path}")

    return "\n".join(lines) + "\n"


def format_markdown(stats: Sequence[FileStat], *, threshold: int, top: int) -> str:
    over = [s for s in stats if s.lines >= threshold]
    lines: list[str] = []
    lines.append("# Large files report")
    lines.append(f"Threshold: **{threshold}** lines")
    lines.append("")

    lines.append(f"## Files >= {threshold} lines ({len(over)})")
    lines.append("")
    lines.append("| Lines | Path |")
    lines.append("| ---: | --- |")
    for s in over[:top]:
        lines.append(f"| {s.lines} | `{s.path}` |")
    if len(over) > top:
        lines.append(f"\n_Showing first {top} of {len(over)} files over threshold._")

    lines.append("")
    lines.append(f"## Top {min(top, len(stats))} files")
    lines.append("")
    lines.append("| Lines | Path |")
    lines.append("| ---: | --- |")
    for s in stats[:top]:
        lines.append(f"| {s.lines} | `{s.path}` |")

    return "\n".join(lines) + "\n"


def format_json(stats: Sequence[FileStat], *, threshold: int, top: int) -> str:
    over = [s for s in stats if s.lines >= threshold]
    payload = {
        "threshold": threshold,
        "over_threshold": [asdict(s) for s in over],
        "top": [asdict(s) for s in stats[:top]],
        "total_scanned": len(stats),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=500,
        help="Line-count threshold for reporting (default: 500)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Limit number of rows shown in each table/list (default: 30)",
    )
    parser.add_argument(
        "--ext",
        action="append",
        default=[".py"],
        help="File extension(s) to include (repeatable). Default: .py",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include all file extensions (overrides --ext).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name(s) to exclude (repeatable).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "md", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write output to a file instead of stdout",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    root: Path = args.root
    threshold: int = args.threshold
    top: int = args.top
    fmt: OutputFormat = args.format

    exclude_dir_names = set(DEFAULT_EXCLUDE_DIR_NAMES)
    exclude_dir_names.update(args.exclude_dir)

    exts = set() if args.include_all else {e if e.startswith(".") else f".{e}" for e in args.ext}

    stats = collect_file_stats(root=root, exts=exts, exclude_dir_names=exclude_dir_names)

    if fmt == "text":
        out = format_text(stats, threshold=threshold, top=top)
    elif fmt == "md":
        out = format_markdown(stats, threshold=threshold, top=top)
    else:
        out = format_json(stats, threshold=threshold, top=top)

    if args.output is not None:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out, end="")

    # Exit with code 2 if there are files over the threshold.
    # This makes it easy to wire into CI if desired.
    return 2 if any(s.lines >= threshold for s in stats) else 0


if __name__ == "__main__":
    raise SystemExit(main())
