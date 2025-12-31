#!/bin/bash
# CI Pipeline Verification Script
# This script simulates the GitHub Actions CI pipeline locally

set -e  # Exit on error

echo "=========================================="
echo "CI Pipeline Verification"
echo "=========================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print success
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Prefer the project venv if present, otherwise fall back to whatever Python is available.
PYTHON_BIN=""
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    error "No Python interpreter found (tried .venv/bin/python, python, python3)"
fi

echo "Step 1: Installing dependencies..."
"$PYTHON_BIN" -m pip install --upgrade pip --quiet
"$PYTHON_BIN" -m pip install -e . --quiet
"$PYTHON_BIN" -m pip install -r requirements-dev.txt --quiet
"$PYTHON_BIN" -m pip install types-requests types-PyYAML --quiet
success "Dependencies installed"
echo ""

echo "Step 2: Running linting checks..."
echo "  - Checking with ruff..."
"$PYTHON_BIN" -m ruff check src/ tests/ || error "Ruff linting failed"
success "Ruff passed"

echo "  - Checking formatting with black..."
"$PYTHON_BIN" -m black --check src/ tests/ || error "Black formatting check failed"
success "Black passed"

echo "  - Checking import sorting with isort..."
"$PYTHON_BIN" -m isort --check-only src/ tests/ || error "isort check failed"
success "isort passed"
echo ""

echo "Step 3: Running type checking..."
"$PYTHON_BIN" -m mypy src/ || error "mypy type checking failed"
success "mypy passed"
echo ""

echo "Step 4: Running tests with coverage..."
"$PYTHON_BIN" -m pytest --cov=src/github_agent_orchestrator --cov-report=term --cov-report=xml --cov-report=html -v || error "Tests failed"
success "All tests passed"
echo ""

echo "=========================================="
echo "All CI checks passed successfully! ✓"
echo "=========================================="
echo ""
echo "Coverage report: htmlcov/index.html"
echo "Coverage XML: coverage.xml"
