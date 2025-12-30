# Scripts

This directory contains utility scripts for development and CI verification.

## verify-ci.sh

Simulates the GitHub Actions CI pipeline locally. Runs all linting, type checking, and testing steps.

**Usage:**
```bash
./scripts/verify-ci.sh
```

This script will:
1. Install all dependencies (including dev dependencies)
2. Run ruff linting
3. Check code formatting with black
4. Check import sorting with isort
5. Run type checking with mypy
6. Execute all tests with coverage reporting

**Requirements:**
- Python 3.11 or higher
- pip

**Exit Codes:**
- 0: All checks passed
- 1: One or more checks failed

Use this script before pushing changes to ensure CI will pass.
