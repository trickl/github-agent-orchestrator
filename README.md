# GitHub Agent Orchestrator

[![Tests](https://github.com/trickl/github-agent-orchestrator/workflows/Tests/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Lint](https://github.com/trickl/github-agent-orchestrator/workflows/Lint/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A stateful orchestration engine that manages plans, critiques, issues, and incremental PRs using GitHub's coding agents. Supports persistent planning via repo-backed storage and continuous project evolution.

## Features

- **🤖 Pluggable LLM Layer**: Support for OpenAI GPT models and local LLaMA models
- **🔗 GitHub Integration**: Read and create Pull Requests and Issues programmatically
- **💾 Persistent State**: Repo-backed state management with version control support
- **🏗️ Clean Architecture**: Modular design with clear separation of concerns
- **✅ Type Safety**: Full type hints and mypy checking
- **🎨 Code Quality**: Automated linting with ruff, black, and isort
- **🧪 Well Tested**: Comprehensive test suite with pytest
- **📚 Documented**: Complete documentation with Sphinx
- **🚀 CI-Ready**: GitHub Actions workflows for testing and deployment

## Quick Start

### Installation

```bash
pip install github-agent-orchestrator
```

For development:
```bash
git clone https://github.com/trickl/github-agent-orchestrator.git
cd github-agent-orchestrator
pip install -e ".[dev]"
```

With local LLaMA support:
```bash
pip install "github-agent-orchestrator[llama]"
```

### Configuration

Create a `.env` file or set environment variables:

```bash
# LLM Configuration
ORCHESTRATOR_LLM_PROVIDER=openai
ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-...
ORCHESTRATOR_LLM_OPENAI_MODEL=gpt-4

# GitHub Configuration
ORCHESTRATOR_GITHUB_TOKEN=ghp_...
ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo

# State Configuration (optional)
ORCHESTRATOR_STATE_STORAGE_PATH=.state
ORCHESTRATOR_STATE_AUTO_COMMIT=true
```

### Basic Usage

```python
from github_agent_orchestrator import Orchestrator, OrchestratorConfig

# Initialize with default configuration from environment
orchestrator = Orchestrator()

# Process a single task
result = orchestrator.process_task(
    "Implement a new feature for user authentication"
)

print(f"Task: {result['task']}")
print(f"Plan: {result['plan']}")
print(f"Status: {result['status']}")

# Run long-running orchestration
orchestrator.run()
```

### Using Different LLM Providers

#### OpenAI

```python
from github_agent_orchestrator import OrchestratorConfig
from github_agent_orchestrator.core.config import LLMConfig

config = OrchestratorConfig(
    llm=LLMConfig(
        provider="openai",
        openai_api_key="sk-...",
        openai_model="gpt-4",
        openai_temperature=0.7,
    )
)

orchestrator = Orchestrator(config)
```

#### Local LLaMA

```python
from pathlib import Path
from github_agent_orchestrator import OrchestratorConfig
from github_agent_orchestrator.core.config import LLMConfig

config = OrchestratorConfig(
    llm=LLMConfig(
        provider="llama",
        llama_model_path=Path("/path/to/model.gguf"),
        llama_n_ctx=4096,
    )
)

orchestrator = Orchestrator(config)
```

### GitHub Operations

```python
from github_agent_orchestrator.github.client import GitHubClient
from github_agent_orchestrator.core.config import GitHubConfig

config = GitHubConfig(
    token="ghp_...",
    repository="owner/repo",
)

client = GitHubClient(config)

# List open pull requests
prs = client.list_pull_requests(state="open")

# Create a new issue
issue = client.create_issue(
    title="New feature request",
    body="Description of the feature",
    labels=["enhancement"],
)

# Create a pull request
pr = client.create_pull_request(
    title="Implement feature X",
    body="This PR implements feature X",
    head="feature-branch",
    base="main",
)
```

## Architecture

The project follows a clean, modular architecture:

```
src/github_agent_orchestrator/
├── core/           # Core orchestration logic and configuration
├── llm/            # LLM provider abstractions and implementations
├── github/         # GitHub API integration
└── state/          # Persistent state management
```

Key components:

- **Orchestrator**: Main coordination engine
- **LLM Providers**: Pluggable language model backends (OpenAI, LLaMA)
- **GitHub Client**: Wrapper for GitHub API operations
- **State Manager**: Repo-backed persistent state with version control

## Development

### Setup

```bash
# Clone and install
git clone https://github.com/trickl/github-agent-orchestrator.git
cd github-agent-orchestrator
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/github_agent_orchestrator

# Run specific test file
pytest tests/unit/test_config.py
```

### Code Quality

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

## Documentation

Full documentation is available in the `docs/` directory:

- [Architecture](docs/architecture.rst) - System design and components
- [API Reference](docs/api.rst) - Complete API documentation
- [Usage Guide](docs/usage.rst) - Detailed usage examples
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

Build documentation locally:

```bash
cd docs
make html
open _build/html/index.html
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and development timeline.

### Current Status (v0.1.0)
- ✅ Core architecture and project structure
- ✅ LLM abstraction with OpenAI and LLaMA support
- ✅ GitHub integration for PRs and Issues
- ✅ Persistent state management
- ✅ Comprehensive testing and documentation

### Coming Soon (v0.2.0)
- 🚧 Complete orchestration workflow
- 🚧 Task decomposition and planning
- 🚧 Automated code review integration
- 🚧 Enhanced error handling

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Run quality checks (`pre-commit run --all-files`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [OpenAI](https://openai.com/) and [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- GitHub integration via [PyGithub](https://github.com/PyGithub/PyGithub)
- Configuration management with [Pydantic](https://github.com/pydantic/pydantic)

## Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/trickl/github-agent-orchestrator/issues)
- 💬 [Discussions](https://github.com/trickl/github-agent-orchestrator/discussions)

---

Made with ❤️ by the Trickl team
