"""Pydantic models for SQL Query Debugger OpenEnv."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class SQLObservation(BaseModel):
    """Observation returned by the environment."""

    task_id: str = Field(..., description="Current task identifier")
    task_description: str = Field(..., description="What the query should accomplish")
    schema_ddl: str = Field(..., description="Database schema as CREATE TABLE statements")
    sample_data: str = Field(..., description="Sample data showing table contents")
    broken_query: str = Field(..., description="The SQL query that needs fixing")
    error_message: Optional[str] = Field(None, description="Error from last execution attempt")
    expected_output_hint: str = Field(..., description="Description of expected results")
    attempts_remaining: int = Field(..., description="Number of fix attempts left")
    current_step: int = Field(..., description="Current step number")
    max_steps: int = Field(..., description="Maximum steps allowed")
    last_query_result: Optional[str] = Field(None, description="Result from last query execution")
    hints_used: int = Field(0, description="Number of hints requested")
    available_actions: list[str] = Field(
        default_factory=lambda: ["submit_fix", "execute_query", "request_hint"],
        description="Actions the agent can take"
    )


class SQLAction(BaseModel):
    """Action submitted by the agent."""

    action_type: str = Field(
        ...,
        description="Type of action: 'submit_fix', 'execute_query', or 'request_hint'"
    )
    query: Optional[str] = Field(
        None,
        description="The SQL query for submit_fix or execute_query actions"
    )


class SQLReward(BaseModel):
    """Reward signal returned by the environment."""

    value: float = Field(..., ge=0.0, le=1.0, description="Reward value between 0 and 1")
    reason: str = Field(..., description="Explanation of the reward")
    partial_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown of partial scores"
    )


class StepResult(BaseModel):
    """Result of a step in the environment."""

    observation: SQLObservation
    reward: float
    done: bool
    info: dict[str, Any] = Field(default_factory=dict)


class ResetResult(BaseModel):
    """Result of resetting the environment."""

    observation: SQLObservation


class StateResult(BaseModel):
    """Current state of the environment."""

    task_id: str
    current_step: int
    max_steps: int
    done: bool
    total_reward: float
    attempts_used: int
    hints_used: int
