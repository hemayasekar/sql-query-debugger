"""Tests for SQL Query Debugger Environment."""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.models import SQLAction, SQLObservation
from server.environment import SQLDebuggerEnvironment, create_environment, get_available_tasks
from server.tasks import get_task, grade_task, list_tasks, TASKS


class TestTasks:
    """Tests for task definitions and graders."""

    def test_all_tasks_defined(self):
        """Verify all 3 tasks are defined."""
        tasks = list_tasks()
        assert len(tasks) >= 3
        assert "easy_syntax_fix" in tasks
        assert "medium_join_logic" in tasks
        assert "hard_complex_analysis" in tasks

    def test_task_difficulty_progression(self):
        """Verify tasks have correct difficulty levels."""
        easy = get_task("easy_syntax_fix")
        medium = get_task("medium_join_logic")
        hard = get_task("hard_complex_analysis")

        assert easy.difficulty == "easy"
        assert medium.difficulty == "medium"
        assert hard.difficulty == "hard"

        # Max steps should increase with difficulty
        assert easy.max_steps <= medium.max_steps <= hard.max_steps

    def test_grader_returns_valid_score_range(self):
        """Verify graders return scores in [0.0, 1.0]."""
        for task_id in list_tasks():
            # Test with broken query (should get low score)
            task = get_task(task_id)
            score, reason, partial_scores = grade_task(task_id, task.broken_query)

            # Broken query might not execute, so score should be low
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {task_id}"

            # Test with correct query (should get high score)
            score, reason, partial_scores = grade_task(task_id, task.correct_query)
            assert 0.95 <= score <= 1.0, f"Correct query should score ~1.0, got {score} for {task_id}"

    def test_grader_deterministic(self):
        """Verify graders are deterministic."""
        for task_id in list_tasks():
            task = get_task(task_id)

            # Run grader multiple times
            scores = []
            for _ in range(3):
                score, _, _ = grade_task(task_id, task.correct_query)
                scores.append(score)

            # All scores should be identical
            assert len(set(scores)) == 1, f"Grader not deterministic for {task_id}: {scores}"

    def test_partial_scores_structure(self):
        """Verify partial scores have expected components."""
        task = get_task("easy_syntax_fix")
        score, reason, partial_scores = grade_task("easy_syntax_fix", task.correct_query)

        assert "syntax_valid" in partial_scores
        assert "row_count" in partial_scores
        assert "column_count" in partial_scores
        assert "data_correct" in partial_scores


class TestEnvironment:
    """Tests for environment implementation."""

    def test_reset_returns_valid_observation(self):
        """Verify reset returns proper observation."""
        env = create_environment("easy_syntax_fix")
        result = env.reset()

        obs = result.observation
        assert isinstance(obs, SQLObservation)
        assert obs.task_id == "easy_syntax_fix"
        assert obs.current_step == 0
        assert obs.max_steps > 0
        assert obs.schema_ddl is not None
        assert obs.broken_query is not None

        env.close()

    def test_reset_clears_state(self):
        """Verify reset clears episode state."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        # Take some steps
        env.step(SQLAction(action_type="request_hint"))
        env.step(SQLAction(action_type="execute_query", query="SELECT 1"))

        # Reset should clear state
        result = env.reset()
        assert result.observation.current_step == 0
        assert result.observation.hints_used == 0

        state = env.state()
        assert state.current_step == 0
        assert state.hints_used == 0
        assert state.total_reward == 0.0

        env.close()

    def test_step_submit_fix(self):
        """Test submit_fix action."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        task = get_task("easy_syntax_fix")

        # Submit correct fix
        result = env.step(SQLAction(
            action_type="submit_fix",
            query=task.correct_query
        ))

        assert result.done is True, "Episode should end on correct submission"
        assert result.reward > 0, "Correct fix should have positive reward"
        assert "success" in result.info
        assert result.info["success"] is True

        env.close()

    def test_step_execute_query(self):
        """Test execute_query action for exploration."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        # Execute a test query
        result = env.step(SQLAction(
            action_type="execute_query",
            query="SELECT * FROM customers LIMIT 2"
        ))

        assert result.done is False, "execute_query should not end episode"
        assert result.observation.last_query_result is not None
        assert "results" in result.info

        env.close()

    def test_step_request_hint(self):
        """Test request_hint action."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        # Request hints
        result1 = env.step(SQLAction(action_type="request_hint"))
        assert "hint" in result1.info
        assert result1.observation.hints_used == 1

        result2 = env.step(SQLAction(action_type="request_hint"))
        assert result2.observation.hints_used == 2

        env.close()

    def test_max_steps_enforced(self):
        """Verify episode ends at max_steps."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        max_steps = env.max_steps

        # Take max_steps
        for i in range(max_steps + 5):
            result = env.step(SQLAction(action_type="request_hint"))
            if result.done:
                break

        assert result.done is True
        assert env.current_step <= max_steps

        env.close()

    def test_state_returns_current_state(self):
        """Verify state() returns correct state."""
        env = create_environment("medium_join_logic")
        env.reset()

        state = env.state()
        assert state.task_id == "medium_join_logic"
        assert state.current_step == 0
        assert state.done is False

        # Take a step
        env.step(SQLAction(action_type="request_hint"))

        state = env.state()
        assert state.current_step == 1
        assert state.hints_used == 1

        env.close()

    def test_reward_in_valid_range(self):
        """Verify all rewards are within expected range."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        rewards = []
        for _ in range(5):
            result = env.step(SQLAction(
                action_type="submit_fix",
                query="SELECT name FROM customers"
            ))
            rewards.append(result.reward)
            if result.done:
                break

        # Rewards should be bounded
        for r in rewards:
            assert -1.0 <= r <= 2.0, f"Reward {r} seems out of reasonable range"

        env.close()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_action_type(self):
        """Test handling of invalid action type."""
        env = create_environment()
        env.reset()

        result = env.step(SQLAction(action_type="invalid_action"))
        assert "error" in result.info

        env.close()

    def test_submit_without_query(self):
        """Test submit_fix with no query."""
        env = create_environment()
        env.reset()

        result = env.step(SQLAction(action_type="submit_fix", query=None))
        assert "error" in result.info
        assert result.reward < 0

        env.close()

    def test_step_after_done(self):
        """Test stepping after episode is done."""
        env = create_environment()
        env.reset()

        task = get_task("easy_syntax_fix")
        env.step(SQLAction(action_type="submit_fix", query=task.correct_query))

        # Try to step again
        result = env.step(SQLAction(action_type="request_hint"))
        assert result.done is True
        assert result.reward == 0.0

        env.close()

    def test_invalid_sql_query(self):
        """Test handling of invalid SQL."""
        env = create_environment()
        env.reset()

        result = env.step(SQLAction(
            action_type="submit_fix",
            query="NOT VALID SQL AT ALL ;;;"
        ))

        assert result.reward <= 0
        assert result.observation.error_message is not None

        env.close()

    def test_switch_tasks(self):
        """Test switching between tasks."""
        env = create_environment("easy_syntax_fix")
        result = env.reset()
        assert result.observation.task_id == "easy_syntax_fix"

        # Switch to medium task
        result = env.reset("medium_join_logic")
        assert result.observation.task_id == "medium_join_logic"

        # Switch to hard task
        result = env.reset("hard_complex_analysis")
        assert result.observation.task_id == "hard_complex_analysis"

        env.close()


class TestIntegration:
    """Integration tests for the full environment."""

    def test_full_easy_episode(self):
        """Run a complete easy episode."""
        env = create_environment("easy_syntax_fix")
        env.reset()

        task = get_task("easy_syntax_fix")

        # Execute query to see error
        env.step(SQLAction(
            action_type="execute_query",
            query=task.broken_query.strip()
        ))

        # Get a hint
        env.step(SQLAction(action_type="request_hint"))

        # Submit fix
        result = env.step(SQLAction(
            action_type="submit_fix",
            query=task.correct_query
        ))

        assert result.done is True
        assert result.info.get("success") is True
        assert env.state().total_reward > 0

        env.close()

    def test_full_episode_all_tasks(self):
        """Run complete episodes for all tasks."""
        for task_id in list_tasks():
            env = create_environment(task_id)
            env.reset()

            task = get_task(task_id)

            result = env.step(SQLAction(
                action_type="submit_fix",
                query=task.correct_query
            ))

            assert result.done is True, f"Task {task_id} should complete"
            assert result.info.get("success") is True, f"Task {task_id} should succeed"

            env.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
