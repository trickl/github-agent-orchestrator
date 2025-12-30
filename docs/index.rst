GitHub Agent Orchestrator
==========================

Welcome to GitHub Agent Orchestrator's documentation!

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   architecture
   api
   usage
   contributing

Overview
--------

A stateful orchestration engine that manages plans, critiques, issues, and 
incremental PRs using GitHub's coding agents. Supports persistent planning 
via repo-backed storage and continuous project evolution.

Features
--------

* **Pluggable LLM Layer**: Support for OpenAI and local LLaMA models
* **GitHub Integration**: Read and create PRs and Issues
* **Persistent State**: Repo-backed state management with version control
* **Clean Architecture**: Modular design with clear separation of concerns
* **Type Safety**: Full typing support with mypy
* **Code Quality**: Automated linting with ruff, black, and isort
* **CI-Ready**: GitHub Actions workflows for testing and deployment

Quick Start
-----------

Installation
~~~~~~~~~~~~

.. code-block:: bash

   pip install github-agent-orchestrator

Configuration
~~~~~~~~~~~~~

Set environment variables or create a `.env` file:

.. code-block:: bash

   # LLM Configuration
   ORCHESTRATOR_LLM_PROVIDER=openai
   ORCHESTRATOR_LLM_OPENAI_API_KEY=your-api-key
   
   # GitHub Configuration
   ORCHESTRATOR_GITHUB_TOKEN=your-github-token
   ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo

Usage
~~~~~

.. code-block:: python

   from github_agent_orchestrator import Orchestrator, OrchestratorConfig
   
   # Initialize with configuration
   config = OrchestratorConfig()
   orchestrator = Orchestrator(config)
   
   # Process a task
   result = orchestrator.process_task("Implement feature X")
   
   # Run long-running orchestration
   orchestrator.run()

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
