# Scripts

This directory contains utility scripts for development and local verification.

## verify-ci.sh

Runs all linting, type checking, and testing steps locally.

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

Run this script after changes to verify everything still passes.
