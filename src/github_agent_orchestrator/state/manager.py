"""State management for persistent orchestrator state."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from github_agent_orchestrator.core.config import StateConfig

logger = logging.getLogger(__name__)


class OrchestratorState(BaseModel):
    """State model for the orchestrator.

    This model represents the persistent state of the orchestrator,
    including tasks, plans, and execution history.
    """

    version: str = Field(default="1.0.0", description="State schema version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    tasks: list[dict[str, Any]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class StateManager:
    """Manager for persisting and loading orchestrator state.

    Supports repo-backed storage for version-controlled state management.
    """

    def __init__(self, config: StateConfig) -> None:
        """Initialize the state manager.

        Args:
            config: State configuration.
        """
        self.config = config
        self.storage_path = config.storage_path
        self.state_file = self.storage_path / "orchestrator_state.json"

        self.state: OrchestratorState = OrchestratorState()

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"State manager initialized at: {self.storage_path}")

    def load(self) -> OrchestratorState:
        """Load state from persistent storage.

        Returns:
            Loaded state object.
        """
        if not self.state_file.exists():
            logger.info("No existing state found, starting fresh")
            return self.state

        try:
            logger.info(f"Loading state from: {self.state_file}")

            with open(self.state_file) as f:
                data = json.load(f)

            self.state = OrchestratorState(**data)
            logger.info(
                f"State loaded: {len(self.state.tasks)} tasks, " f"{len(self.state.plans)} plans"
            )

        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            logger.warning("Using fresh state")

        return self.state

    def save(self) -> None:
        """Save state to persistent storage."""
        try:
            # Update timestamp
            self.state.updated_at = datetime.now(UTC)

            logger.info(f"Saving state to: {self.state_file}")

            with open(self.state_file, "w") as f:
                json.dump(
                    self.state.model_dump(mode="json"),
                    f,
                    indent=2,
                    default=str,
                )

            logger.info("State saved successfully")

            if self.config.auto_commit:
                self._commit_state()

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def _commit_state(self) -> None:
        """Commit state changes to git (if in a git repository)."""
        try:
            import subprocess

            # Check if we're in a git repository
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.storage_path.parent,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.debug("Not in a git repository, skipping commit")
                return

            # Add and commit state file
            subprocess.run(
                ["git", "add", str(self.state_file)],
                cwd=self.storage_path.parent,
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Update orchestrator state: {self.state.updated_at}",
                ],
                cwd=self.storage_path.parent,
                check=True,
            )

            logger.info("State changes committed to git")

        except subprocess.CalledProcessError as e:
            logger.debug(f"Git commit skipped: {e}")
        except Exception as e:
            logger.warning(f"Failed to commit state: {e}")

    def add_task(self, task: dict[str, Any]) -> None:
        """Add a task to the state.

        Args:
            task: Task data dictionary.
        """
        task["created_at"] = datetime.now(UTC).isoformat()
        self.state.tasks.append(task)
        logger.debug(f"Task added to state: {task.get('task', 'unnamed')}")

    def add_plan(self, plan: dict[str, Any]) -> None:
        """Add a plan to the state.

        Args:
            plan: Plan data dictionary.
        """
        plan["created_at"] = datetime.now(UTC).isoformat()
        self.state.plans.append(plan)
        logger.debug("Plan added to state")

    def add_history_entry(self, entry: dict[str, Any]) -> None:
        """Add a history entry to the state.

        Args:
            entry: History entry dictionary.
        """
        entry["timestamp"] = datetime.now(UTC).isoformat()
        self.state.history.append(entry)
        logger.debug("History entry added to state")

    def get_state(self) -> OrchestratorState:
        """Get the current state.

        Returns:
            Current state object.
        """
        return self.state

    def clear_state(self) -> None:
        """Clear all state data."""
        logger.warning("Clearing all state data")
        self.state = OrchestratorState()
