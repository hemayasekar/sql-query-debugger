"""SQL Query Debugger Environment Implementation."""

import sqlite3
from typing import Any, Optional

from .models import (
    SQLAction,
    SQLObservation,
    StepResult,
    ResetResult,
    StateResult,
)
from .tasks import TaskDefinition, get_task, SQLGrader, list_tasks


class SQLDebuggerEnvironment:
    """
    OpenEnv-compliant environment for SQL query debugging.

    Agents must diagnose and fix broken SQL queries to produce
    the expected results.
    """

    def __init__(self, task_id: str = "easy_syntax_fix"):
        """Initialize the environment with a specific task."""
        self.task_id = task_id
        self.task: Optional[TaskDefinition] = None
        self.grader: Optional[SQLGrader] = None

        # Episode state
        self.current_step: int = 0
        self.max_steps: int = 10
        self.done: bool = False
        self.total_reward: float = 0.0
        self.attempts_used: int = 0
        self.hints_used: int = 0
        self.last_error: Optional[str] = None
        self.last_query_result: Optional[str] = None
        self.best_score: float = 0.0
        self.history: list[dict[str, Any]] = []

    def reset(self, task_id: Optional[str] = None) -> ResetResult:
        """
        Reset the environment to initial state.

        Args:
            task_id: Optional task to switch to

        Returns:
            ResetResult with initial observation
        """
        if task_id:
            self.task_id = task_id

        self.task = get_task(self.task_id)
        self.grader = SQLGrader(self.task)
        self.grader.setup_database()

        self.current_step = 0
        self.max_steps = self.task.max_steps
        self.done = False
        self.total_reward = 0.0
        self.attempts_used = 0
        self.hints_used = 0
        self.last_error = None
        self.last_query_result = None
        self.best_score = 0.0
        self.history = []

        # Execute broken query to show initial error
        success, _, error = self.grader.execute_query(self.task.broken_query)
        if not success:
            self.last_error = error

        observation = self._make_observation()
        return ResetResult(observation=observation)

    def step(self, action: SQLAction) -> StepResult:
        """
        Execute an action and return the result.

        Args:
            action: The action to execute

        Returns:
            StepResult with observation, reward, done, and info
        """
        if self.done:
            return StepResult(
                observation=self._make_observation(),
                reward=0.0,
                done=True,
                info={"error": "Episode already finished"}
            )

        self.current_step += 1
        reward = 0.0
        info: dict[str, Any] = {}

        if action.action_type == "submit_fix":
            reward, info = self._handle_submit_fix(action.query)
        elif action.action_type == "execute_query":
            reward, info = self._handle_execute_query(action.query)
        elif action.action_type == "request_hint":
            reward, info = self._handle_request_hint()
        else:
            info["error"] = f"Unknown action type: {action.action_type}"
            reward = -0.05  # Small penalty for invalid action

        # Record history
        self.history.append({
            "step": self.current_step,
            "action": action.model_dump(),
            "reward": reward,
            "done": self.done
        })

        self.total_reward += reward

        # Check if max steps reached
        if self.current_step >= self.max_steps and not self.done:
            self.done = True
            info["termination_reason"] = "max_steps_reached"

        observation = self._make_observation()
        return StepResult(
            observation=observation,
            reward=reward,
            done=self.done,
            info=info
        )

    def state(self) -> StateResult:
        """Return current environment state."""
        return StateResult(
            task_id=self.task_id,
            current_step=self.current_step,
            max_steps=self.max_steps,
            done=self.done,
            total_reward=self.total_reward,
            attempts_used=self.attempts_used,
            hints_used=self.hints_used
        )

    def _make_observation(self) -> SQLObservation:
        """Create observation from current state."""
        sample_data = self._format_sample_data()

        return SQLObservation(
            task_id=self.task_id,
            task_description=self.task.description,
            schema_ddl=self.task.schema_ddl.strip(),
            sample_data=sample_data,
            broken_query=self.task.broken_query.strip(),
            error_message=self.last_error,
            expected_output_hint=self.task.expected_output_hint,
            attempts_remaining=self.max_steps - self.current_step,
            current_step=self.current_step,
            max_steps=self.max_steps,
            last_query_result=self.last_query_result,
            hints_used=self.hints_used,
            available_actions=["submit_fix", "execute_query", "request_hint"]
        )

    def _format_sample_data(self) -> str:
        """Format sample data as readable table."""
        if not self.grader or not self.grader.conn:
            return "Sample data not available"

        lines = []
        cursor = self.grader.conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            lines.append(f"\n-- {table} --")
            lines.append(" | ".join(columns))
            lines.append("-" * 50)
            for row in rows:
                lines.append(" | ".join(str(v) for v in row))

        return "\n".join(lines)

    def _handle_submit_fix(self, query: Optional[str]) -> tuple[float, dict[str, Any]]:
        """Handle a fix submission."""
        info: dict[str, Any] = {}

        if not query:
            info["error"] = "No query provided"
            return -0.05, info

        self.attempts_used += 1

        # Grade the submission
        score, reason, partial_scores = self.grader.grade(query)
        info["score"] = score
        info["reason"] = reason
        info["partial_scores"] = partial_scores

        # Calculate reward based on improvement and absolute score
        reward = self._calculate_reward(score, partial_scores)

        if score >= 0.99:
            self.done = True
            info["success"] = True
            # Bonus for solving with fewer steps
            steps_remaining = self.max_steps - self.current_step
            efficiency_bonus = 0.1 * (steps_remaining / self.max_steps)
            reward += efficiency_bonus
            info["efficiency_bonus"] = efficiency_bonus
        else:
            info["success"] = False
            # Store last error for feedback
            success, results, error = self.grader.execute_query(query)
            if not success:
                self.last_error = error
            else:
                self.last_error = f"Query executed but results incorrect: {reason}"
                if results:
                    self.last_query_result = str(results[:5])  # Show first 5 rows

        # Update best score
        if score > self.best_score:
            self.best_score = score

        return reward, info

    def _handle_execute_query(self, query: Optional[str]) -> tuple[float, dict[str, Any]]:
        """Handle a test query execution (not a submission)."""
        info: dict[str, Any] = {}

        if not query:
            info["error"] = "No query provided"
            return -0.02, info

        success, results, error = self.grader.execute_query(query)

        if success:
            self.last_error = None
            self.last_query_result = str(results[:10]) if results else "No results"
            info["results"] = results[:10] if results else []
            info["row_count"] = len(results) if results else 0
            # Small positive reward for successful exploration
            return 0.01, info
        else:
            self.last_error = error
            self.last_query_result = None
            info["error"] = error
            return 0.0, info  # No penalty for exploration

    def _handle_request_hint(self) -> tuple[float, dict[str, Any]]:
        """Handle a hint request."""
        info: dict[str, Any] = {}

        if self.hints_used >= len(self.task.hints):
            info["hint"] = "No more hints available"
            return 0.0, info

        hint = self.task.hints[self.hints_used]
        self.hints_used += 1
        info["hint"] = hint
        info["hints_remaining"] = len(self.task.hints) - self.hints_used

        # Small penalty for using hints
        return -0.02, info

    def _calculate_reward(self, score: float, partial_scores: dict[str, float]) -> float:
        """
        Calculate reward based on score and progress.

        Reward shaping to encourage:
        - Syntactically valid queries
        - Getting closer to correct results
        - Improvement over previous attempts
        """
        # Base reward from score
        reward = score * 0.5

        # Improvement bonus
        if score > self.best_score:
            improvement = score - self.best_score
            reward += improvement * 0.3

        # Partial progress bonuses
        if partial_scores.get("syntax_valid", 0) > 0:
            reward += 0.05  # Bonus for valid syntax
        if partial_scores.get("row_count", 0) > 0:
            reward += 0.03  # Bonus for correct row count
        if partial_scores.get("data_correct", 0) > 0.25:
            reward += 0.05  # Bonus for partial data match

        # Penalty for repeated low scores
        if self.attempts_used > 3 and score < 0.3:
            reward -= 0.05

        return round(reward, 4)

    def close(self):
        """Clean up resources."""
        if self.grader:
            self.grader.cleanup()


# Factory function for creating environment instances
def create_environment(task_id: str = "easy_syntax_fix") -> SQLDebuggerEnvironment:
    """Create a new SQL Debugger environment instance."""
    return SQLDebuggerEnvironment(task_id=task_id)


def get_available_tasks() -> list[str]:
    """Get list of available task IDs."""
    return list_tasks()
