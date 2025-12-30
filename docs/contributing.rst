Contributing
============

We welcome contributions to GitHub Agent Orchestrator!

Development Setup
-----------------

1. Fork the repository
2. Clone your fork:

.. code-block:: bash

   git clone https://github.com/your-username/github-agent-orchestrator.git
   cd github-agent-orchestrator

3. Install development dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

4. Install pre-commit hooks:

.. code-block:: bash

   pre-commit install

Code Style
----------

We follow these style guidelines:

* **PEP 8**: Python code style
* **Black**: Code formatting (line length: 100)
* **isort**: Import sorting
* **Ruff**: Fast Python linter
* **mypy**: Static type checking

Before committing, ensure your code passes all checks:

.. code-block:: bash

   # Linting
   ruff check src/ tests/
   
   # Formatting
   black src/ tests/
   isort src/ tests/
   
   # Type checking
   mypy src/

Testing
-------

Write tests for all new features:

.. code-block:: bash

   # Run tests
   pytest
   
   # With coverage
   pytest --cov=src/github_agent_orchestrator --cov-report=html

* Place unit tests in `tests/unit/`
* Place integration tests in `tests/integration/`
* Aim for >80% code coverage

Pull Request Process
--------------------

1. Create a feature branch:

.. code-block:: bash

   git checkout -b feature/your-feature-name

2. Make your changes and commit:

.. code-block:: bash

   git add .
   git commit -m "Add feature: description"

3. Push to your fork:

.. code-block:: bash

   git push origin feature/your-feature-name

4. Open a Pull Request on GitHub

5. Ensure CI checks pass:
   - Tests
   - Linting
   - Type checking
   - Coverage

Commit Messages
---------------

Follow conventional commits:

* `feat:` New feature
* `fix:` Bug fix
* `docs:` Documentation changes
* `test:` Test changes
* `refactor:` Code refactoring
* `style:` Code style changes
* `chore:` Build/tooling changes

Example:

.. code-block:: text

   feat: add support for Claude AI provider
   
   - Implement ClaudeProvider class
   - Add configuration for Anthropic API
   - Add tests for new provider

Documentation
-------------

Update documentation for new features:

* Add docstrings to all public functions/classes
* Update relevant `.rst` files in `docs/`
* Build docs locally to verify:

.. code-block:: bash

   cd docs
   make html
   open _build/html/index.html

Issues
------

When reporting issues, include:

* Python version
* Operating system
* Steps to reproduce
* Expected vs actual behavior
* Error messages/stack traces

Code Review
-----------

All contributions go through code review:

* Address reviewer feedback
* Keep discussions focused and professional
* Update based on suggestions

License
-------

By contributing, you agree that your contributions will be licensed under 
the MIT License.
