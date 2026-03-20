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
        default: main
        type: string

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

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Setup GitHub Agent Orchestrator runtime
        uses: trickl/github-agent-orchestrator/.github/actions/setup-orchestrator@main
        with:
          version: latest

      - name: Run orchestrator iteration
        env:
          ORCHESTRATOR_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          orchestrator run --repo ${{ github.repository }}
"""
