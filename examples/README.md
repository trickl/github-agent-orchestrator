# Examples

This directory contains example scripts demonstrating how to use the GitHub Agent Orchestrator.

## Available Examples

### basic_usage.py

Programmatic issue creation (Phase 1/1A) showing:

* settings loaded from `.env`
* GitHub issue creation
* idempotency derived from GitHub state (no local runtime JSON persistence)

Run with:
```bash
python examples/basic_usage.py --repo owner/repo --title "Hello" --body "From examples/" --labels agent
```

For full functionality, set environment variables:
```bash
export ORCHESTRATOR_GITHUB_TOKEN=ghp_...

python examples/basic_usage.py --repo owner/repo --title "Hello" --body "From examples/" --labels agent
```

## Additional Resources

See the main [documentation](../docs/) for more detailed usage information.
