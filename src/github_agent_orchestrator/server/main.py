"""Run the REST server.

This keeps deployment simple for now:

- `orchestrator-server` (console script)
- or `python -m github_agent_orchestrator.server`

The app serves OpenAPI at `/openapi.json` and interactive docs at `/docs`.
"""

from __future__ import annotations

import os

import uvicorn

from github_agent_orchestrator.server.app import create_app


def main() -> None:
    host = os.getenv("ORCHESTRATOR_HOST", "127.0.0.1")
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
