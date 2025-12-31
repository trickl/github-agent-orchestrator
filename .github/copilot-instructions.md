# Copilot Instructions

## Purpose

GitHub Copilot must help produce high-quality, maintainable Python code that aligns with modern software engineering standards. It should optimize for clarity, correctness, testability, and incremental improvement.

## System invariants (do not violate)

This repository implements an **autonomous development process** that is driven by **artefacts** (files and issues), not by hidden reasoning in the orchestrator.

The orchestrator does two and only two things:

1. **Create issues** (from well-defined templates and intent).
2. **Materialise issues from files** (promote queued artefacts into GitHub issues).

It does *not* decide content, reason about solutions, or interpret meaning beyond basic classification and routing.

All “thinking” happens inside Copilot-authored PRs.

### Canonical planning folders

These folders are the contract between the user, Copilot PR work, and the orchestrator:

```
/planning
  /vision
    goal.md
  /state
    system_capabilities.md
  /reviews
    review-YYYY-MM-DD.md
  /issue_queue
    pending/
    processed/
```

The `/planning/issue_queue` boundary is **the heart of the system**.

### The four canonical issue types (never mix)

1) **Gap Analysis (Plan → Build)**

- Purpose: compare `goal.md` vs `system_capabilities.md` and identify the next development step.
- Output: exactly one file in `/planning/issue_queue/pending/dev-<timestamp>.md`.
- Constraints: **no code changes**, **no GitHub issue creation**, output is a **candidate task**, not a fix.

2) **Development Task (Build Something)**

- Input: a file from `/planning/issue_queue/pending/`.
- Output: code + tests, and an updated `/planning/state/system_capabilities.md`.
- Promotion: the orchestrator converts the queue file into a GitHub issue, assigns to Copilot, and moves the file to `processed/` (or archives it) after issue creation.

3) **Review Task (Critique)**

- Purpose: assess the system from one specific lens (architecture, correctness, mission alignment, capability completeness).
- Output: exactly one file in `/planning/reviews/`.
- Constraints: **analysis only**: no fixes and no new tasks.

4) **Review Consumption (Critique → Action)**

- Input: one specific review file.
- Output: one or more files in `/planning/issue_queue/pending/review-<timestamp>-<n>.md`.
- Each file must map to **one actionable concern**.

### One subtle but crucial rule

The orchestrator **never reads review content semantically**. It only identifies files, routes them, and promotes them.

If you violate this, you reintroduce hidden intelligence and lose debuggability.

### Orchestrator loop (rate-limited)

- One issue per cycle.
- Scan `/planning/issue_queue/pending`.
- If a file exists: promote the *next* file → issue → move to processed → assign to Copilot → **exit**.
- If no file exists: optionally create a *meta-issue* (gap analysis, system state update, review) → sleep/poll.

### User role

The user owns exactly one artefact:

- `/planning/vision/goal.md`

Everything else is derived.

## General Development Principles

- Prefer simple, explicit, readable code.
- Follow PEP8, use type hints, and maintain consistent formatting.
- Prefer clear architecture over clever shortcuts.
- Avoid unnecessary abstractions; keep code minimal but extensible.

## Code Quality & Structure

- Enforce ≤ 500 lines per file.
  - If a file grows beyond ~400 lines, begin refactoring into coherent modules.
- Functions should be small, single-purpose, and named precisely.
- Prefer dependency injection and composition over large monolithic classes.
- Always write code that is easy to delete and evolve.

## Refactoring Behavior

When refactoring:

- Prefer breaking changes if it results in simplicity, unless explicitly asked to preserve compatibility.
- Do not retain legacy behaviors or backwards-compatibility layers unless explicitly requested.
- Replace old structures cleanly; avoid transitional duplication.
- Remove deprecated patterns and anti-patterns aggressively.

## Deleting Unused Code

- Delete unused functions, code paths, feature flags, dead branches, and redundant abstractions.
- Remove commented-out code.
- Prefer deleting over hiding "just in case".
- If something might matter later, document it instead of leaving it in the codebase.

## Testing & Reliability

- Every meaningful feature must include unit tests.
- New behavior must come with tests.
- Refactors must not reduce coverage.
- Prefer deterministic, reliable tests over brittle intelligent ones.

## Documentation & Comments

- Document public functions and modules with concise docstrings.
- Use comments to explain why, not what.
- Keep README and architecture docs aligned with behavior.

## Linting & Style

This project uses the following linting and formatting tools:

- **ruff**: For fast Python linting (configured in `pyproject.toml`)
- **black**: For code formatting (100 character line length)
- **isort**: For import sorting (black-compatible profile)
- **mypy**: For static type checking

Assume linting tools run (black, ruff, isort, mypy or equivalent).

- Produce lint-clean code proactively.
- Prefer consistent formatting over stylistic creativity.
- Follow the configuration in `pyproject.toml`:
  - Line length: 100 characters
  - Python version: 3.11+
  - Use type hints for all function signatures
  - Avoid `Any` types where possible

## Security & Stability

- Avoid unsafe eval, shell execution, insecure network handling.
- Prefer principle of least privilege.
- Never hard-code secrets.
- Use environment variables or secure configuration management for sensitive data.
- Validate and sanitize all external inputs.
