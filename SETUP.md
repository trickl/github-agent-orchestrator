# Setup Guide

This guide will help you set up and start using the GitHub Agent Orchestrator.

## Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- Git
- A GitHub account (for GitHub integration)
- OpenAI API key (for OpenAI provider) or a local LLaMA model file (for LLaMA provider)

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/trickl/github-agent-orchestrator.git
cd github-agent-orchestrator
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package:
```bash
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install github-agent-orchestrator
```

With LLaMA support:
```bash
pip install "github-agent-orchestrator[llama]"
```

## Configuration

### Method 1: Using CLI (Recommended)

Initialize configuration with the CLI:

```bash
orchestrator init --provider openai
```

This creates a `.env` file with all configuration options.

Edit `.env` and add your credentials:

```bash
# LLM Configuration
ORCHESTRATOR_LLM_PROVIDER=openai
ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-your-actual-key-here
ORCHESTRATOR_LLM_OPENAI_MODEL=gpt-4

# GitHub Configuration
ORCHESTRATOR_GITHUB_TOKEN=ghp-your-actual-token-here
ORCHESTRATOR_GITHUB_REPOSITORY=your-username/your-repo
```

### Method 2: Environment Variables

Set environment variables directly:

```bash
export ORCHESTRATOR_LLM_PROVIDER=openai
export ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-...
export ORCHESTRATOR_LLM_OPENAI_MODEL=gpt-4

export ORCHESTRATOR_GITHUB_TOKEN=ghp-...
export ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo

export ORCHESTRATOR_STATE_STORAGE_PATH=.state
export ORCHESTRATOR_STATE_AUTO_COMMIT=true
```

### Method 3: Programmatic Configuration

```python
from pathlib import Path
from github_agent_orchestrator import OrchestratorConfig
from github_agent_orchestrator.core.config import LLMConfig, GitHubConfig

config = OrchestratorConfig(
    llm=LLMConfig(
        provider="openai",
        openai_api_key="sk-...",
        openai_model="gpt-4",
    ),
    github=GitHubConfig(
        token="ghp-...",
        repository="owner/repo",
    ),
)
```

## Getting API Keys

### OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key and save it securely

### GitHub Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes:
   - `repo` (full repository access)
   - `workflow` (if you need workflow access)
4. Click "Generate token"
5. Copy the token and save it securely

## Usage

### CLI Commands

Process a single task:
```bash
orchestrator task "Create a Python function to calculate fibonacci numbers"
```

Run the orchestrator loop:
```bash
orchestrator run
```

With debug mode:
```bash
orchestrator task "Your task" --debug
```

### Python API

```python
from github_agent_orchestrator import Orchestrator

# Initialize orchestrator
orchestrator = Orchestrator()

# Process a task
result = orchestrator.process_task("Your task description")

print(f"Task: {result['task']}")
print(f"Plan: {result['plan']}")
print(f"Status: {result['status']}")
```

## Verification

### Test Your Setup

Run the example script:

```bash
python examples/basic_usage.py
```

### Run Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=src/github_agent_orchestrator
```

### Check Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting
black --check src/ tests/

# Type checking
mypy src/
```

## LLaMA Setup (Optional)

To use local LLaMA models:

1. Install llama-cpp-python:
```bash
pip install llama-cpp-python
```

2. Download a GGUF model file (e.g., from Hugging Face)

3. Configure the path:
```bash
export ORCHESTRATOR_LLM_PROVIDER=llama
export ORCHESTRATOR_LLM_LLAMA_MODEL_PATH=/path/to/model.gguf
export ORCHESTRATOR_LLM_LLAMA_N_CTX=4096
```

## Troubleshooting

### Import Errors

If you get import errors, ensure the package is installed:
```bash
pip install -e .
```

### API Key Issues

If authentication fails:
- Check your API keys are correct
- Verify keys have the necessary permissions
- Check for typos in environment variable names

### Connection Issues

If you can't connect to APIs:
- Check your internet connection
- Verify firewall settings
- Check API service status pages

### State Issues

If state is not persisting:
- Check directory permissions for `.state` directory
- Verify `auto_commit` setting if using git
- Check logs for error messages

## Next Steps

1. Read the [Architecture Documentation](docs/architecture.rst)
2. Explore the [Usage Guide](docs/usage.rst)
3. Check out [Examples](examples/)
4. Review the [Roadmap](ROADMAP.md)
5. Join our community discussions

## Getting Help

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/trickl/github-agent-orchestrator/issues)
- 💬 [Discussions](https://github.com/trickl/github-agent-orchestrator/discussions)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to the project.
