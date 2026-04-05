#!/usr/bin/env python3
"""
SQL Query Debugger - Baseline Inference Script
===============================================

Runs an LLM agent against the SQL Query Debugger environment to produce
baseline scores for all three tasks.

MANDATORY Environment Variables:
- HF_TOKEN or API_KEY: Your API key for the LLM service
- API_BASE_URL: The API endpoint (default: HuggingFace router)
- MODEL_NAME: Model identifier (default: Qwen/Qwen2.5-72B-Instruct)

STDOUT FORMAT:
- [START] task=<task_name> env=<benchmark> model=<model_name>
- [STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
- [END] success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
"""

import os
import sys
import textwrap
import json
from typing import Any, Optional

import httpx
from openai import OpenAI

# =============================================================================
# Configuration
# =============================================================================

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

# Environment configuration
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")
BENCHMARK_NAME = "sql-query-debugger"

# Inference settings
TEMPERATURE = 0.3
MAX_TOKENS = 1024

# Tasks to run (in order of difficulty)
TASKS = ["easy_syntax_fix", "medium_join_logic", "hard_complex_analysis"]

# =============================================================================
# Logging Functions (MANDATORY FORMAT)
# =============================================================================


def log_start(task: str, env: str, model: str) -> None:
    """Log episode start."""
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    """Log a step result."""
    error_val = error if error else "null"
    done_val = str(done).lower()
    # Escape action string for logging
    action_safe = action.replace("\n", " ").replace("\r", "")[:100]
    print(
        f"[STEP] step={step} action={action_safe} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    """Log episode end."""
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def log_debug(msg: str) -> None:
    """Log debug message."""
    print(f"[DEBUG] {msg}", flush=True)


# =============================================================================
# Environment Client
# =============================================================================


class SQLDebuggerClient:
    """HTTP client for the SQL Query Debugger environment."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    def reset(self, task_id: str) -> dict[str, Any]:
        """Reset environment with specified task."""
        response = self.client.post(
            f"{self.base_url}/reset",
            json={"task_id": task_id}
        )
        response.raise_for_status()
        return response.json()

    def step(self, action_type: str, query: Optional[str] = None) -> dict[str, Any]:
        """Execute an action."""
        payload = {"action_type": action_type}
        if query:
            payload["query"] = query
        response = self.client.post(
            f"{self.base_url}/step",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def state(self) -> dict[str, Any]:
        """Get current state."""
        response = self.client.get(f"{self.base_url}/state")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the client."""
        self.client.close()


# =============================================================================
# LLM Agent
# =============================================================================


SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL debugger. Your task is to fix broken SQL queries.

    You will receive:
    1. A database schema (CREATE TABLE statements)
    2. Sample data showing what's in the tables
    3. A broken SQL query that needs fixing
    4. A description of what the query should accomplish
    5. Error messages or hints about what's wrong

    Your goal is to diagnose the issues and submit a corrected query.

    ACTIONS YOU CAN TAKE:
    1. submit_fix - Submit your fixed SQL query (this is graded)
    2. execute_query - Test a query to see what it returns (no grading)
    3. request_hint - Get a hint about what's wrong

    RESPONSE FORMAT:
    Respond with a JSON object containing:
    {
        "reasoning": "Brief explanation of the issue and your fix",
        "action_type": "submit_fix" | "execute_query" | "request_hint",
        "query": "Your SQL query (required for submit_fix and execute_query)"
    }

    TIPS:
    - Check for common SQL errors: typos, wrong JOIN columns, missing GROUP BY columns
    - Use execute_query to test your hypotheses before submit_fix
    - Pay attention to error messages and query results
    - The query should match the expected output description

    Always respond with valid JSON only, no markdown code blocks.
""").strip()


def build_user_prompt(observation: dict[str, Any], history: list[str]) -> str:
    """Build the user prompt from observation."""
    history_text = "\n".join(history[-5:]) if history else "None"

    return textwrap.dedent(f"""
        === DATABASE SCHEMA ===
        {observation['schema_ddl']}

        === SAMPLE DATA ===
        {observation['sample_data']}

        === BROKEN QUERY ===
        {observation['broken_query']}

        === TASK ===
        {observation['task_description']}

        === EXPECTED OUTPUT ===
        {observation['expected_output_hint']}

        === CURRENT STATE ===
        - Step: {observation['current_step']} / {observation['max_steps']}
        - Last error: {observation.get('error_message') or 'None'}
        - Last query result: {observation.get('last_query_result') or 'None'}
        - Hints used: {observation.get('hints_used', 0)}

        === RECENT HISTORY ===
        {history_text}

        Analyze the broken query and respond with your action as JSON.
    """).strip()


def get_llm_action(
    client: OpenAI,
    observation: dict[str, Any],
    history: list[str]
) -> tuple[str, Optional[str], str]:
    """
    Get action from LLM.

    Returns:
        (action_type, query, reasoning)
    """
    user_prompt = build_user_prompt(observation, history)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()

        # Try to parse JSON response
        # Handle potential markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        parsed = json.loads(content)
        action_type = parsed.get("action_type", "submit_fix")
        query = parsed.get("query")
        reasoning = parsed.get("reasoning", "")

        return action_type, query, reasoning

    except json.JSONDecodeError as e:
        log_debug(f"JSON parse error: {e}")
        # Try to extract query from response
        content = response.choices[0].message.content or ""
        if "SELECT" in content.upper() or "select" in content:
            # Extract SQL query
            lines = content.split("\n")
            sql_lines = [l for l in lines if any(kw in l.upper() for kw in ["SELECT", "FROM", "WHERE", "JOIN", "GROUP", "ORDER"])]
            if sql_lines:
                return "submit_fix", " ".join(sql_lines), "Extracted from response"
        return "request_hint", None, "Failed to parse response"

    except Exception as e:
        log_debug(f"LLM request failed: {e}")
        return "request_hint", None, f"Error: {e}"


# =============================================================================
# Episode Runner
# =============================================================================


def run_episode(
    env: SQLDebuggerClient,
    llm: OpenAI,
    task_id: str
) -> tuple[float, list[float], int, bool]:
    """
    Run a single episode on a task.

    Returns:
        (final_score, rewards_list, steps_taken, success)
    """
    log_start(task=task_id, env=BENCHMARK_NAME, model=MODEL_NAME)

    rewards: list[float] = []
    history: list[str] = []
    steps = 0
    success = False
    final_score = 0.0

    try:
        # Reset environment
        result = env.reset(task_id)
        observation = result["observation"]
        done = False

        max_steps = observation.get("max_steps", 15)

        while not done and steps < max_steps:
            steps += 1

            # Get action from LLM
            action_type, query, reasoning = get_llm_action(llm, observation, history)

            # Execute action
            step_result = env.step(action_type, query)

            observation = step_result["observation"]
            reward = step_result.get("reward", 0.0)
            done = step_result.get("done", False)
            info = step_result.get("info", {})

            rewards.append(reward)

            # Log step
            error = info.get("error")
            action_str = f"{action_type}({query[:50] if query else ''})"
            log_step(step=steps, action=action_str, reward=reward, done=done, error=error)

            # Update history
            history.append(f"Step {steps}: {action_type} -> reward={reward:.2f}, info={info}")

            # Check for success
            if info.get("success", False):
                success = True
                final_score = info.get("score", 1.0)
                break

        # Calculate final score if not already set
        if not success:
            state = env.state()
            final_score = max(rewards) if rewards else 0.0

    except Exception as e:
        log_debug(f"Episode error: {e}")
        final_score = 0.0

    # Ensure score is in [0, 1]
    final_score = max(0.0, min(1.0, final_score))

    log_end(success=success, steps=steps, score=final_score, rewards=rewards)

    return final_score, rewards, steps, success


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Run baseline inference on all tasks."""
    if not API_KEY:
        print("ERROR: HF_TOKEN or API_KEY environment variable not set", file=sys.stderr)
        return 1

    # Initialize clients
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    env = SQLDebuggerClient(ENV_BASE_URL)

    results: dict[str, dict[str, Any]] = {}

    try:
        for task_id in TASKS:
            print(f"\n{'='*60}", flush=True)
            print(f"Running task: {task_id}", flush=True)
            print(f"{'='*60}\n", flush=True)

            score, rewards, steps, success = run_episode(env, llm, task_id)

            results[task_id] = {
                "score": score,
                "rewards": rewards,
                "steps": steps,
                "success": success,
            }

    finally:
        env.close()

    # Print summary
    print(f"\n{'='*60}", flush=True)
    print("BASELINE RESULTS SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)

    total_score = 0.0
    for task_id, result in results.items():
        print(f"{task_id}: score={result['score']:.3f}, steps={result['steps']}, success={result['success']}", flush=True)
        total_score += result["score"]

    avg_score = total_score / len(TASKS) if TASKS else 0.0
    print(f"\nAverage score: {avg_score:.3f}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
