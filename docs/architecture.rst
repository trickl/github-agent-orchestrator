Architecture
============

Overview
--------

The GitHub Agent Orchestrator is built with a modular architecture that 
separates concerns into distinct layers:

Core Components
---------------

Orchestrator
~~~~~~~~~~~~

The main orchestrator (`github_agent_orchestrator.core.orchestrator.Orchestrator`) 
coordinates between all components and manages the high-level workflow.

**Responsibilities:**
* Initialize and coordinate all subsystems
* Manage task processing lifecycle
* Handle long-running orchestration workflows

Configuration
~~~~~~~~~~~~~

Configuration is managed through Pydantic models 
(`github_agent_orchestrator.core.config.OrchestratorConfig`) that support:

* Environment variable loading
* .env file support
* Type validation
* Nested configuration structures

LLM Layer
---------

The LLM layer provides a pluggable abstraction for different language models:

Provider Interface
~~~~~~~~~~~~~~~~~~

`github_agent_orchestrator.llm.provider.LLMProvider` defines the abstract 
interface that all providers must implement:

* `generate()`: Text completion
* `chat()`: Chat-based interaction
* `count_tokens()`: Token counting

Implementations
~~~~~~~~~~~~~~~

1. **OpenAI Provider**: Uses OpenAI's API for GPT models
2. **LLaMA Provider**: Uses local LLaMA models via llama-cpp-python

Factory Pattern
~~~~~~~~~~~~~~~

`github_agent_orchestrator.llm.factory.LLMFactory` creates appropriate 
provider instances based on configuration.

GitHub Integration
------------------

The GitHub integration layer (`github_agent_orchestrator.github.client.GitHubClient`) 
provides methods for:

* Reading and creating Pull Requests
* Reading and creating Issues
* Repository management
* Authentication handling

State Management
----------------

State Manager
~~~~~~~~~~~~~

`github_agent_orchestrator.state.manager.StateManager` provides:

* JSON-based state persistence
* Repo-backed storage with git integration
* Versioned state schema
* Automatic state commits (optional)

State Model
~~~~~~~~~~~

`github_agent_orchestrator.state.manager.OrchestratorState` defines:

* Tasks: List of tracked tasks
* Plans: Generated execution plans
* History: Execution history
* Metadata: Additional contextual information

Data Flow
---------

1. **Initialization**: Load configuration and initialize components
2. **State Loading**: Load persistent state from storage
3. **Task Processing**: 
   - Receive task description
   - Generate plan using LLM
   - Interact with GitHub as needed
   - Update state
4. **State Persistence**: Save state to storage (with optional git commit)
5. **Long-running Loop**: Continue processing tasks until completion

Extension Points
----------------

The architecture supports extension through:

* **Custom LLM Providers**: Implement `LLMProvider` interface
* **Custom State Backends**: Extend `StateManager`
* **Custom GitHub Operations**: Extend `GitHubClient`
