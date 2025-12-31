# Setup Guide

This guide will help you set up and start using the GitHub Agent Orchestrator.

## Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- Git
- A GitHub account (for GitHub integration)
- A GitHub token with permission to create issues in your target repository

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

The orchestrator reads configuration from environment variables and/or a local `.env` file.

Create a `.env` in the project root:

```bash
# Required
ORCHESTRATOR_GITHUB_TOKEN=ghp-your-actual-token-here

# Optional (defaults shown)
GITHUB_BASE_URL=https://api.github.com
LOG_LEVEL=INFO
AGENT_STATE_PATH=agent_state
```

Repository selection is intentionally not stored in `.env`; you pass it per command via `--repo`.

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

Create a GitHub issue:
```bash
orchestrator create-issue \
    --repo "owner/repo" \
    --title "Test issue" \
    --body "Created by the orchestrator" \
    --labels "agent,test"
```

### REST server + dashboard UI

This repo includes a small FastAPI server (Python) and a React dashboard (Vite) in `ui/`.

#### What the UI should point to

- The dashboard expects the API at **`/api`** (same origin).
- In development, the Vite dev server proxies `/api/*` to the Python server.
- In production, the Python server can serve the built UI and the API from the same process.

#### Start the REST server

The server can start without a GitHub token for local-only dashboard features (planning docs, rules, timeline, reading local issue state). Endpoints that call GitHub (e.g. refreshing PRs) still require `ORCHESTRATOR_GITHUB_TOKEN`.

```bash
python -m github_agent_orchestrator.server
```

By default it binds to `127.0.0.1:8000`. Override via:

```bash
ORCHESTRATOR_HOST=127.0.0.1 ORCHESTRATOR_PORT=8000 python -m github_agent_orchestrator.server
```

API docs are available at:

- `http://127.0.0.1:8000/api/docs`

#### Start the UI (dev)

In another terminal:

```bash
cd ui
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and will proxy `/api/*` to `http://127.0.0.1:8000`.

#### Serve the UI from the Python server (production-ish)

Build the UI:

```bash
cd ui
npm run build
```

Then start the Python server again and open:

- `http://127.0.0.1:8000/`

## Verification

### Test Your Setup

Run the example script:

```bash
python examples/basic_usage.py --repo owner/repo --title "Hello" --body "From examples/" --labels agent
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
- Check directory permissions for the `AGENT_STATE_PATH` directory
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
