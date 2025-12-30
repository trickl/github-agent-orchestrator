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

echo "Step 1: Installing dependencies..."
python -m pip install --upgrade pip --quiet
pip install -e . --quiet
pip install -r requirements-dev.txt --quiet
pip install types-requests types-PyYAML --quiet
success "Dependencies installed"
echo ""

echo "Step 2: Running linting checks..."
echo "  - Checking with ruff..."
ruff check src/ tests/ || error "Ruff linting failed"
success "Ruff passed"

echo "  - Checking formatting with black..."
black --check src/ tests/ || error "Black formatting check failed"
success "Black passed"

echo "  - Checking import sorting with isort..."
isort --check-only src/ tests/ || error "isort check failed"
success "isort passed"
echo ""

echo "Step 3: Running type checking..."
mypy src/ || error "mypy type checking failed"
success "mypy passed"
echo ""

echo "Step 4: Running tests with coverage..."
pytest --cov=src/github_agent_orchestrator --cov-report=term --cov-report=xml --cov-report=html -v || error "Tests failed"
success "All tests passed"
echo ""

echo "=========================================="
echo "All CI checks passed successfully! ✓"
echo "=========================================="
echo ""
echo "Coverage report: htmlcov/index.html"
echo "Coverage XML: coverage.xml"
