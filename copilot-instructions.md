# Copilot Instructions

## Purpose

GitHub Copilot must help produce high-quality, maintainable Python code that aligns with modern software engineering standards. It should optimize for clarity, correctness, testability, and incremental improvement.

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
- Do not retain legacy behaviours or backwards-compatibility layers unless explicitly requested.
- Replace old structures cleanly; avoid transitional duplication.
- Remove deprecated patterns and anti-patterns aggressively.

## Deleting Unused Code

- Delete unused functions, code paths, feature flags, dead branches, and redundant abstractions.
- Remove commented-out code.
- Prefer deleting over hiding "just in case".
- If something might matter later, document it instead of leaving it in the codebase.

## Testing & Reliability

- Every meaningful feature must include unit tests.
- New behaviour must come with tests.
- Refactors must not reduce coverage.
- Prefer deterministic, reliable tests over brittle intelligent ones.

## Documentation & Comments

- Document public functions and modules with concise docstrings.
- Use comments to explain why, not what.
- Keep README and architecture docs aligned with behaviour.

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
