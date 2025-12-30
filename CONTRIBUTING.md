# Contributing to GitHub Agent Orchestrator

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A GitHub account

### Setup Development Environment

1. Fork the repository on GitHub

2. Clone your fork:
```bash
git clone https://github.com/your-username/github-agent-orchestrator.git
cd github-agent-orchestrator
```

3. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. Install dependencies:
```bash
pip install -e ".[dev]"
```

5. Install pre-commit hooks:
```bash
pre-commit install
```

6. Verify installation:
```bash
pytest
ruff check src/ tests/
mypy src/
```

## Development Workflow

### Creating a Branch

Create a feature branch from `main`:

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `test/` - Test additions or modifications
- `refactor/` - Code refactoring

### Making Changes

1. Make your changes in small, logical commits
2. Write or update tests for your changes
3. Update documentation as needed
4. Ensure all tests pass
5. Run linters and formatters

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/github_agent_orchestrator

# Run specific test file
pytest tests/unit/test_config.py

# Run specific test
pytest tests/unit/test_config.py::test_llm_config_defaults
```

### Code Quality Checks

Before committing, ensure your code passes all checks:

```bash
# Linting
ruff check src/ tests/

# Auto-fix linting issues
ruff check --fix src/ tests/

# Formatting
black src/ tests/

# Import sorting
isort src/ tests/

# Type checking
mypy src/
```

Or run pre-commit manually:
```bash
pre-commit run --all-files
```

## Code Style

### Python Style Guide

We follow PEP 8 with some modifications:

- Line length: 100 characters (not 79)
- Use type hints for all function signatures
- Use docstrings for all public functions and classes

### Docstring Format

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of the function.
    
    Longer description if needed. Can span multiple lines.
    
    Args:
        param1: Description of param1.
        param2: Description of param2.
        
    Returns:
        Description of return value.
        
    Raises:
        ValueError: When something is wrong.
    """
    pass
```

### Type Hints

Always use type hints:

```python
from typing import Any

def process_data(data: dict[str, Any]) -> list[str]:
    """Process data and return results."""
    pass
```

## Testing

### Test Structure

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Name test files `test_*.py`
- Name test functions `test_*`

### Writing Tests

```python
import pytest
from github_agent_orchestrator.core.config import LLMConfig

def test_llm_config_defaults() -> None:
    """Test LLM config default values."""
    config = LLMConfig(openai_api_key="test-key")
    
    assert config.provider == "openai"
    assert config.openai_model == "gpt-4"
```

### Test Coverage

- Aim for >90% code coverage
- All new features must have tests
- Bug fixes should include regression tests

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes
- Keep docstrings up to date with code changes
- Include examples in docstrings when helpful

### Project Documentation

Documentation is in the `docs/` directory using Sphinx:

```bash
cd docs
make html
```

Update relevant `.rst` files when adding features.

### README Updates

Update the README.md if your changes:
- Add new features
- Change installation process
- Modify configuration options
- Affect usage examples

## Pull Request Process

### Before Submitting

1. Ensure all tests pass
2. Update documentation
3. Add entry to CHANGELOG.md (if applicable)
4. Rebase on latest main branch
5. Run all quality checks

### Submitting a PR

1. Push your branch to your fork
2. Open a Pull Request on GitHub
3. Fill out the PR template completely
4. Link any related issues

### PR Title Format

Use conventional commits format:

- `feat: add support for Claude AI provider`
- `fix: resolve token counting issue in LLaMA provider`
- `docs: update installation instructions`
- `test: add tests for state manager`
- `refactor: simplify LLM factory logic`

### PR Description

Include:
- Summary of changes
- Motivation and context
- How changes were tested
- Screenshots (for UI changes)
- Breaking changes (if any)

### Code Review Process

- Address all reviewer comments
- Keep discussions focused and professional
- Update PR based on feedback
- Request re-review when ready

### Merging

- PRs require at least one approval
- All CI checks must pass
- Squash commits when merging (usually)

## Issue Guidelines

### Reporting Bugs

Include:
- Python version and OS
- Steps to reproduce
- Expected vs actual behavior
- Error messages and stack traces
- Minimal reproducible example

### Requesting Features

Include:
- Clear description of the feature
- Use cases and motivation
- Proposed implementation (optional)
- Willingness to contribute

### Asking Questions

- Check existing issues and documentation first
- Use GitHub Discussions for general questions
- Be specific and provide context

## Development Tips

### Environment Variables

Create a `.env` file for development:

```bash
ORCHESTRATOR_LLM_PROVIDER=openai
ORCHESTRATOR_LLM_OPENAI_API_KEY=your-key-here
ORCHESTRATOR_GITHUB_TOKEN=your-token-here
ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo
```

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or set environment variable:

```bash
export ORCHESTRATOR_LOG_LEVEL=DEBUG
export ORCHESTRATOR_DEBUG=true
```

### Running Integration Tests

Integration tests may require:
- Valid API keys
- Network access
- External services

Skip integration tests during development:

```bash
pytest tests/unit/
```

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in documentation

## Questions?

- Open a GitHub Discussion
- Check existing issues
- Review documentation

Thank you for contributing! 🎉
