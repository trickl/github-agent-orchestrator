"""Run the REST server.

This keeps deployment simple for now:

- `orchestrator-server` (console script)
- or `python -m github_agent_orchestrator.server`

The app serves OpenAPI at `/openapi.json` and interactive docs at `/docs`.
"""

from __future__ import annotations

import argparse
import os

import uvicorn

from github_agent_orchestrator.server.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="orchestrator-server")
    parser.add_argument(
        "--host",
        default=os.getenv("ORCHESTRATOR_HOST", "127.0.0.1"),
        help="Host interface to bind (defaults to ORCHESTRATOR_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORCHESTRATOR_PORT", "8000")),
        help="Port to bind (defaults to ORCHESTRATOR_PORT)",
    )
    parser.add_argument(
        "--loop-mode",
        choices=["build", "review"],
        default=os.getenv("ORCHESTRATOR_LOOP_MODE", "build"),
        help=(
            "Loop mode: 'build' (gap-analysis + capability updates) or 'review' "
            "(review consumption + review actions updates). Defaults to ORCHESTRATOR_LOOP_MODE."
        ),
    )
    args = parser.parse_args()

    # ServerSettings reads from env at app creation time.
    os.environ["ORCHESTRATOR_LOOP_MODE"] = str(args.loop_mode)

    app = create_app()
    uvicorn.run(app, host=str(args.host), port=int(args.port))


if __name__ == "__main__":
    main()
