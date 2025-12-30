#!/usr/bin/env python3
"""Command-line interface for GitHub Agent Orchestrator."""

import argparse
import sys
from pathlib import Path

from github_agent_orchestrator import Orchestrator, OrchestratorConfig


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GitHub Agent Orchestrator - Autonomous agent coordination",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version="github-agent-orchestrator 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the orchestrator")
    run_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # Task command
    task_parser = subparsers.add_parser("task", help="Process a single task")
    task_parser.add_argument("description", help="Task description")
    task_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize configuration")
    init_parser.add_argument(
        "--provider",
        choices=["openai", "llama"],
        default="openai",
        help="LLM provider to use",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "init":
            init_config(args)
        elif args.command == "run":
            run_orchestrator(args)
        elif args.command == "task":
            process_task(args)
        else:
            print(f"Unknown command: {args.command}")
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if hasattr(args, "debug") and args.debug:
            raise
        return 1


def init_config(args: argparse.Namespace) -> None:
    """Initialize configuration file."""
    env_file = Path(".env")

    if env_file.exists():
        print(f"Configuration file {env_file} already exists")
        response = input("Overwrite? (y/N): ")
        if response.lower() != "y":
            print("Aborted")
            return

    template = f"""# GitHub Agent Orchestrator Configuration

# LLM Configuration
ORCHESTRATOR_LLM_PROVIDER={args.provider}
ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-your-openai-key-here
ORCHESTRATOR_LLM_OPENAI_MODEL=gpt-4

# For LLaMA provider:
# ORCHESTRATOR_LLM_LLAMA_MODEL_PATH=/path/to/model.gguf
# ORCHESTRATOR_LLM_LLAMA_N_CTX=4096

# GitHub Configuration
ORCHESTRATOR_GITHUB_TOKEN=ghp-your-github-token-here
ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo

# State Configuration
ORCHESTRATOR_STATE_STORAGE_PATH=.state
ORCHESTRATOR_STATE_AUTO_COMMIT=true

# Logging
ORCHESTRATOR_LOG_LEVEL=INFO
ORCHESTRATOR_DEBUG=false
"""

    env_file.write_text(template)
    print(f"Created configuration file: {env_file}")
    print("\nNext steps:")
    print("1. Edit .env and add your API keys")
    print("2. Run: orchestrator task 'your task description'")


def run_orchestrator(args: argparse.Namespace) -> None:
    """Run the orchestrator main loop."""
    config = OrchestratorConfig(
        debug=args.debug,
        log_level="DEBUG" if args.debug else "INFO",
    )

    orchestrator = Orchestrator(config)
    orchestrator.run()

    print("Orchestrator run completed")


def process_task(args: argparse.Namespace) -> None:
    """Process a single task."""
    config = OrchestratorConfig(
        debug=args.debug,
        log_level="DEBUG" if args.debug else "INFO",
    )

    orchestrator = Orchestrator(config)
    result = orchestrator.process_task(args.description)

    print("\n" + "=" * 60)
    print(f"Task: {result['task']}")
    print(f"Status: {result['status']}")
    print("=" * 60)
    print("\nPlan:")
    print(result["plan"])
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
