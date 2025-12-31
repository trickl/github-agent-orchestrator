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

Minimal, local-first orchestrator (Phase 1/1A).

This increment focuses on configuration, logging, and a small GitHub integration surface
centered on issue creation with local persistence.

Features
--------

* **.env + env var config** via Pydantic Settings
* **Structured JSON logs** using stdlib logging
* **GitHub issue creation** (PyGithub wrapper)
* **Local JSON state** persisted to `agent_state/issues.json`

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

   # Required
   ORCHESTRATOR_GITHUB_TOKEN=your-github-token

   # Optional (defaults shown)
   GITHUB_BASE_URL=https://api.github.com
   LOG_LEVEL=INFO
   AGENT_STATE_PATH=agent_state

Repository selection is passed per command via ``--repo``.

Usage
~~~~~

.. code-block:: bash

   orchestrator create-issue \
     --repo "owner/repo" \
     --title "Hello" \
     --body "Created by the orchestrator" \
     --labels "agent,phase-1"

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
