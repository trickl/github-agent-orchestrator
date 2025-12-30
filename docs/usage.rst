Usage Guide
===========

Installation
------------

Basic Installation
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install github-agent-orchestrator

Development Installation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/trickl/github-agent-orchestrator.git
   cd github-agent-orchestrator
   pip install -e ".[dev]"

With LLaMA Support
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install "github-agent-orchestrator[llama]"

Configuration
-------------

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

Create a `.env` file in your project root:

.. code-block:: bash

   # LLM Configuration
   ORCHESTRATOR_LLM_PROVIDER=openai
   ORCHESTRATOR_LLM_OPENAI_API_KEY=sk-...
   ORCHESTRATOR_LLM_OPENAI_MODEL=gpt-4
   
   # GitHub Configuration
   ORCHESTRATOR_GITHUB_TOKEN=ghp_...
   ORCHESTRATOR_GITHUB_REPOSITORY=owner/repo
   
   # State Configuration
   ORCHESTRATOR_STATE_STORAGE_PATH=.state
   ORCHESTRATOR_STATE_AUTO_COMMIT=true

Programmatic Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator import OrchestratorConfig
   from github_agent_orchestrator.core.config import LLMConfig, GitHubConfig
   
   config = OrchestratorConfig(
       log_level="INFO",
       llm=LLMConfig(
           provider="openai",
           openai_api_key="sk-...",
           openai_model="gpt-4",
       ),
       github=GitHubConfig(
           token="ghp_...",
           repository="owner/repo",
       ),
   )

Basic Usage
-----------

Initialize Orchestrator
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator import Orchestrator
   
   orchestrator = Orchestrator()

Process a Task
~~~~~~~~~~~~~~

.. code-block:: python

   result = orchestrator.process_task(
       "Implement a new feature for user authentication"
   )
   
   print(f"Task: {result['task']}")
   print(f"Plan: {result['plan']}")
   print(f"Status: {result['status']}")

Long-running Orchestration
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   orchestrator.run()

Advanced Usage
--------------

Using OpenAI Provider
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator.llm.factory import LLMFactory
   from github_agent_orchestrator.core.config import LLMConfig
   
   config = LLMConfig(
       provider="openai",
       openai_api_key="sk-...",
       openai_model="gpt-4",
       openai_temperature=0.8,
   )
   
   llm = LLMFactory.create(config)
   response = llm.generate("Write a Python function to calculate fibonacci")

Using LLaMA Provider
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator.llm.factory import LLMFactory
   from github_agent_orchestrator.core.config import LLMConfig
   from pathlib import Path
   
   config = LLMConfig(
       provider="llama",
       llama_model_path=Path("/path/to/model.gguf"),
       llama_n_ctx=4096,
   )
   
   llm = LLMFactory.create(config)
   response = llm.generate("Write a Python function to calculate fibonacci")

GitHub Operations
~~~~~~~~~~~~~~~~~

.. code-block:: python

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

State Management
~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator.state.manager import StateManager
   from github_agent_orchestrator.core.config import StateConfig
   from pathlib import Path
   
   config = StateConfig(
       storage_path=Path(".state"),
       auto_commit=True,
   )
   
   manager = StateManager(config)
   
   # Load state
   state = manager.load()
   
   # Add task
   manager.add_task({
       "task": "Implement authentication",
       "status": "pending",
   })
   
   # Save state
   manager.save()

Testing
-------

Run Tests
~~~~~~~~~

.. code-block:: bash

   # Run all tests
   pytest
   
   # Run with coverage
   pytest --cov=src/github_agent_orchestrator
   
   # Run specific test file
   pytest tests/unit/test_config.py

Linting and Formatting
----------------------

.. code-block:: bash

   # Run ruff linter
   ruff check src/ tests/
   
   # Auto-fix issues
   ruff check --fix src/ tests/
   
   # Format with black
   black src/ tests/
   
   # Sort imports with isort
   isort src/ tests/
   
   # Type checking with mypy
   mypy src/

Pre-commit Hooks
~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Install pre-commit hooks
   pre-commit install
   
   # Run manually
   pre-commit run --all-files
