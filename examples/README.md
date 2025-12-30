# Examples

This directory contains example scripts demonstrating how to use the GitHub Agent Orchestrator.

## Available Examples

### basic_usage.py

Comprehensive examples showing:
- Basic orchestrator usage
- Custom configuration
- Direct LLM provider usage
- GitHub client operations
- State management

Run with:
```bash
python examples/basic_usage.py
```

For full functionality, set environment variables:
```bash
export ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-...
export ORCHESTRATOR_GITHUB_TOKEN=ghp_...
export ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo

python examples/basic_usage.py
```

## Additional Resources

See the main [documentation](../docs/) for more detailed usage information.
