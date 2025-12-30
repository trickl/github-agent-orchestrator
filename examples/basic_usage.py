#!/usr/bin/env python3
"""Example usage of the GitHub Agent Orchestrator.

This script demonstrates how to use the orchestrator with different
LLM providers and GitHub integration.
"""

import logging
import os
from pathlib import Path

from github_agent_orchestrator import Orchestrator, OrchestratorConfig
from github_agent_orchestrator.core.config import GitHubConfig, LLMConfig, StateConfig


def example_basic_usage() -> None:
    """Example: Basic usage with environment variables."""
    print("=== Basic Usage Example ===\n")

    # Initialize orchestrator (reads from environment)
    orchestrator = Orchestrator()

    # Process a simple task
    result = orchestrator.process_task("Create a simple Python function to calculate factorial")

    print(f"Task: {result['task']}")
    print(f"Status: {result['status']}")
    print(f"Plan:\n{result['plan']}\n")


def example_custom_config() -> None:
    """Example: Using custom configuration."""
    print("=== Custom Configuration Example ===\n")

    # Create custom configuration
    config = OrchestratorConfig(
        log_level="DEBUG",
        debug=True,
        llm=LLMConfig(
            provider="openai",
            openai_api_key=os.getenv("OPENAI_API_KEY", "test-key"),
            openai_model="gpt-4",
            openai_temperature=0.8,
        ),
        github=GitHubConfig(
            token=os.getenv("GITHUB_TOKEN"),
            repository=os.getenv("GITHUB_REPOSITORY"),
        ),
        state=StateConfig(storage_path=Path(".state"), auto_commit=False),
    )

    orchestrator = Orchestrator(config)

    # Process a task
    result = orchestrator.process_task("Design a REST API for a todo application")

    print(f"Task: {result['task']}")
    print(f"Status: {result['status']}\n")


def example_llm_direct() -> None:
    """Example: Using LLM provider directly."""
    print("=== Direct LLM Usage Example ===\n")

    from github_agent_orchestrator.llm.factory import LLMFactory

    # Create LLM provider
    config = LLMConfig(
        provider="openai",
        openai_api_key=os.getenv("OPENAI_API_KEY", "test-key"),
        openai_model="gpt-4",
    )

    try:
        llm = LLMFactory.create(config)

        # Generate text
        response = llm.generate("Write a haiku about coding")
        print(f"Response: {response}\n")

        # Chat interface
        messages = [
            {"role": "user", "content": "What is Python?"},
        ]
        chat_response = llm.chat(messages)
        print(f"Chat Response: {chat_response}\n")
    except Exception as e:
        print(f"LLM example requires valid API key: {e}\n")


def example_github_client() -> None:
    """Example: Using GitHub client directly."""
    print("=== GitHub Client Example ===\n")

    from github_agent_orchestrator.github.client import GitHubClient

    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")

    if not token or not repository:
        print("GitHub example requires GITHUB_TOKEN and GITHUB_REPOSITORY env vars\n")
        return

    try:
        config = GitHubConfig(token=token, repository=repository)
        client = GitHubClient(config)

        # List open pull requests
        prs = client.list_pull_requests(state="open")
        print(f"Found {len(prs)} open pull requests")

        # List open issues
        issues = client.list_issues(state="open")
        print(f"Found {len(issues)} open issues\n")

        client.close()
    except Exception as e:
        print(f"GitHub example failed: {e}\n")


def example_state_management() -> None:
    """Example: Using state manager directly."""
    print("=== State Management Example ===\n")

    from github_agent_orchestrator.state.manager import StateManager

    config = StateConfig(storage_path=Path("/tmp/example-state"), auto_commit=False)

    manager = StateManager(config)

    # Add some data
    manager.add_task(
        {"task": "Implement user authentication", "status": "in_progress", "priority": "high"}
    )

    manager.add_plan(
        {
            "plan": "Authentication Implementation",
            "steps": [
                "Design user model",
                "Implement password hashing",
                "Create login endpoint",
                "Add JWT tokens",
                "Write tests",
            ],
        }
    )

    # Save state
    manager.save()

    # Load state
    state = manager.load()
    print(f"Loaded state with {len(state.tasks)} tasks and {len(state.plans)} plans")
    print(f"First task: {state.tasks[0]['task']}\n")


def main() -> None:
    """Run all examples."""
    logging.basicConfig(level=logging.INFO)

    print("GitHub Agent Orchestrator - Usage Examples")
    print("=" * 50)
    print()

    # Run examples that don't require API keys
    example_state_management()

    # Examples that may require credentials (will handle gracefully)
    example_custom_config()
    example_llm_direct()
    example_github_client()

    print("=" * 50)
    print("\nExamples completed!")
    print("\nTo run with real API keys, set environment variables:")
    print("  export ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-...")
    print("  export ORCHESTRATOR_GITHUB_TOKEN=ghp_...")
    print("  export ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo")


if __name__ == "__main__":
    main()
