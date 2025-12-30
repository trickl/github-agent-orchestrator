"""Unit tests for state manager."""

import json
import pytest
from pathlib import Path

from github_agent_orchestrator.state.manager import StateManager, OrchestratorState
from github_agent_orchestrator.core.config import StateConfig


def test_state_manager_initialization(temp_state_dir: Path) -> None:
    """Test state manager initialization."""
    config = StateConfig(storage_path=temp_state_dir, auto_commit=False)
    manager = StateManager(config)
    
    assert manager.storage_path == temp_state_dir
    assert manager.state_file == temp_state_dir / "orchestrator_state.json"
    assert isinstance(manager.state, OrchestratorState)


def test_state_save_and_load(temp_state_dir: Path) -> None:
    """Test saving and loading state."""
    config = StateConfig(storage_path=temp_state_dir, auto_commit=False)
    manager = StateManager(config)
    
    # Add some data
    manager.add_task({"task": "test task", "status": "pending"})
    manager.add_plan({"plan": "test plan"})
    
    # Save state
    manager.save()
    
    # Create new manager and load
    manager2 = StateManager(config)
    state = manager2.load()
    
    assert len(state.tasks) == 1
    assert len(state.plans) == 1
    assert state.tasks[0]["task"] == "test task"


def test_add_task(temp_state_dir: Path) -> None:
    """Test adding tasks to state."""
    config = StateConfig(storage_path=temp_state_dir, auto_commit=False)
    manager = StateManager(config)
    
    task = {"task": "test task", "status": "pending"}
    manager.add_task(task)
    
    assert len(manager.state.tasks) == 1
    assert manager.state.tasks[0]["task"] == "test task"
    assert "created_at" in manager.state.tasks[0]


def test_add_plan(temp_state_dir: Path) -> None:
    """Test adding plans to state."""
    config = StateConfig(storage_path=temp_state_dir, auto_commit=False)
    manager = StateManager(config)
    
    plan = {"plan": "test plan", "steps": ["step1", "step2"]}
    manager.add_plan(plan)
    
    assert len(manager.state.plans) == 1
    assert manager.state.plans[0]["plan"] == "test plan"
    assert "created_at" in manager.state.plans[0]


def test_clear_state(temp_state_dir: Path) -> None:
    """Test clearing state."""
    config = StateConfig(storage_path=temp_state_dir, auto_commit=False)
    manager = StateManager(config)
    
    manager.add_task({"task": "test"})
    manager.add_plan({"plan": "test"})
    
    assert len(manager.state.tasks) > 0
    assert len(manager.state.plans) > 0
    
    manager.clear_state()
    
    assert len(manager.state.tasks) == 0
    assert len(manager.state.plans) == 0
