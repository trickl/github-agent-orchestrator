#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${REPO_ROOT}/.venv/bin/activate"

export ORCHESTRATOR_AUTO_PROMOTE_ENABLED="false"

python -m uvicorn github_agent_orchestrator.server.app:create_app --factory --reload --host 127.0.0.1 --port 8000
