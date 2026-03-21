"""Workflow templates provisioned into target repositories."""

from __future__ import annotations


ORCHESTRATOR_WORKFLOW_PATH = ".github/workflows/orchestrator.yml"


def render_orchestrator_workflow() -> str:
    """Render the default orchestrator workflow for target repositories."""

    return """name: Orchestrator Iteration

on:
  workflow_dispatch:
    inputs:
      ref:
        description: Git ref to run orchestration against
        required: false
        default: ''
        type: string
  workflow_run:
    workflows: ["Copilot coding agent"]
    types: [completed]
  schedule:
    - cron: '*/10 * * * *'

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  orchestrate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout target repository
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.inputs.ref || github.ref_name }}

      - name: Report resolved branch/ref
        run: |
          echo "workflow_input_ref=${{ github.event.inputs.ref || '<empty>' }}"
          echo "github_ref=${{ github.ref }}"
          echo "github_ref_name=${{ github.ref_name }}"
          echo "repository=${{ github.repository }}"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Checkout orchestrator runtime source
        uses: actions/checkout@v4
        with:
          repository: trickl/github-agent-orchestrator
          ref: main
          path: .orchestrator-runtime

      - name: Install GitHub Agent Orchestrator runtime (editable)
        run: |
          set -euo pipefail
          python -m pip install --upgrade --no-cache-dir -e ./.orchestrator-runtime
          python -c 'import github_agent_orchestrator as g; print(f"orchestrator_version={g.__version__}")'

      - name: Run orchestrator iteration
        id: orchestrate
        env:
          ORCHESTRATOR_GITHUB_TOKEN: ${{ secrets.ORCHESTRATOR_GITHUB_TOKEN || secrets.GITHUB_TOKEN }}
        run: |
          set +e
          gao run --repo ${{ github.repository }} --mode auto --heal-orphans
          exit_code=$?
          set -e

          echo "exit_code=$exit_code" >> "$GITHUB_OUTPUT"

          if [[ "$exit_code" -eq 3 ]]; then
            echo "No actionable stage detected; treating as successful no-op."
            exit 0
          fi

          exit "$exit_code"

      - name: Re-dispatch orchestrator for follow-up
        if: steps.orchestrate.outputs.exit_code == '0'
        env:
          GH_TOKEN: ${{ secrets.ORCHESTRATOR_GITHUB_TOKEN || secrets.GITHUB_TOKEN }}
        run: |
          echo "Orchestrator took action; scheduling follow-up dispatch..."
          sleep 10
          gh workflow run orchestrator.yml --repo ${{ github.repository }} || echo "Self-dispatch failed; rely on schedule trigger."
"""
