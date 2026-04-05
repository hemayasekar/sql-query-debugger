"""FastAPI server for SQL Query Debugger OpenEnv."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .environment import (
    SQLDebuggerEnvironment,
    create_environment,
    get_available_tasks,
)
from .models import SQLAction, SQLObservation, StepResult, ResetResult, StateResult


# Global environment instance (per-session in production you'd use session management)
_env: Optional[SQLDebuggerEnvironment] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global _env
    _env = create_environment()
    yield
    if _env:
        _env.close()


app = FastAPI(
    title="SQL Query Debugger",
    description="An OpenEnv environment for training AI agents to debug SQL queries",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for HuggingFace Spaces
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models for API
class ResetRequest(BaseModel):
    task_id: Optional[str] = None


class StepRequest(BaseModel):
    action_type: str
    query: Optional[str] = None


class TaskInfo(BaseModel):
    task_id: str
    difficulty: str
    description: str
    max_steps: int


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        environment="sql-query-debugger",
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        environment="sql-query-debugger",
        version="1.0.0"
    )


@app.get("/tasks", response_model=list[TaskInfo])
async def list_tasks():
    """List all available tasks."""
    from .tasks import TASKS

    return [
        TaskInfo(
            task_id=task.task_id,
            difficulty=task.difficulty,
            description=task.description,
            max_steps=task.max_steps
        )
        for task in TASKS.values()
    ]


@app.post("/reset", response_model=ResetResult)
async def reset(request: ResetRequest = None):
    """Reset the environment to initial state."""
    global _env

    if request is None:
        request = ResetRequest()

    task_id = request.task_id or "easy_syntax_fix"

    # Validate task ID
    available = get_available_tasks()
    if task_id not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task: {task_id}. Available: {available}"
        )

    # Clean up old environment
    if _env:
        _env.close()

    # Create fresh environment
    _env = create_environment(task_id)
    result = _env.reset(task_id)

    return result


@app.post("/step", response_model=StepResult)
async def step(request: StepRequest):
    """Execute an action in the environment."""
    global _env

    if _env is None:
        raise HTTPException(
            status_code=400,
            detail="Environment not initialized. Call /reset first."
        )

    action = SQLAction(
        action_type=request.action_type,
        query=request.query
    )

    result = _env.step(action)
    return result


@app.get("/state", response_model=StateResult)
async def state():
    """Get current environment state."""
    global _env

    if _env is None:
        raise HTTPException(
            status_code=400,
            detail="Environment not initialized. Call /reset first."
        )

    return _env.state()


# =============================================================================
# OpenEnv Spec Compliance Endpoints
# =============================================================================


@app.get("/openenv/info")
async def openenv_info():
    """Return OpenEnv metadata."""
    return {
        "name": "sql-query-debugger",
        "version": "1.0.0",
        "description": "Debug and fix broken SQL queries",
        "author": "OpenEnv Community",
        "tasks": get_available_tasks(),
        "spec_version": "1.0"
    }


@app.get("/openenv/observation_space")
async def observation_space():
    """Return observation space definition."""
    return SQLObservation.model_json_schema()


@app.get("/openenv/action_space")
async def action_space():
    """Return action space definition."""
    return SQLAction.model_json_schema()


def main():
    """Entry point for the server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
