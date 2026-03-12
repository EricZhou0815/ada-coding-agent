"""Tests for orchestration/plan_orchestrator.py — Phase 3 full pipeline."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from orchestration.plan_orchestrator import PlanOrchestrator
from planning.models import ImplementationPlan, Task, TaskType


@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.reset_conversation = Mock()
    llm.conversation_history = []
    return llm


@pytest.fixture 
def sample_story():
    return {
        "story_id": "STORY-1",
        "title": "Password reset feature",
        "description": "Users can reset password",
        "acceptance_criteria": ["reset works"],
    }


def _plan_response(tasks):
    """Build a mock LLM response with a valid plan."""
    plan = {
        "feature_title": "Test Feature",
        "feature_description": "Test description",
        "success_criteria": ["works"],
        "tasks": tasks,
    }
    return {"content": f"```json\n{json.dumps(plan)}\n```"}


class TestPlanOrchestratorSuccess:
    @patch("execution.run_execution.ExecutionEngine.execute_task", return_value=True)
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_single_task_success(self, mock_plan, mock_exec, mock_llm, sample_story):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[Task("t1", "p1", "Task 1", "Do something", TaskType.BACKEND)],
        )

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_story(sample_story, "/repo")

        assert result is True
        mock_plan.assert_called_once()
        mock_exec.assert_called_once()

    @patch("execution.run_execution.ExecutionEngine.execute_task", return_value=True)
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_multi_task_chain_success(self, mock_plan, mock_exec, mock_llm, sample_story):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[
                Task("t1", "p1", "Schema", "Migration", TaskType.DATABASE),
                Task("t2", "p1", "API", "Endpoint", TaskType.API, dependencies=["t1"]),
                Task("t3", "p1", "Tests", "Unit tests", TaskType.TEST, dependencies=["t2"]),
            ],
        )

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_story(sample_story, "/repo")

        assert result is True
        assert mock_exec.call_count == 3


class TestPlanOrchestratorFailure:
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_planning_failure_returns_false(self, mock_plan, mock_llm, sample_story):
        mock_plan.return_value = None

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_story(sample_story, "/repo")

        assert result is False

    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_empty_tasks_returns_false(self, mock_plan, mock_llm, sample_story):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[],
        )

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_story(sample_story, "/repo")

        assert result is False

    @patch("execution.run_execution.ExecutionEngine.execute_task", return_value=False)
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_task_execution_failure(self, mock_plan, mock_exec, mock_llm, sample_story):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[Task("t1", "p1", "Task", "Desc", TaskType.BACKEND)],
        )

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws", max_task_retries=1)
        result = orch.execute_story(sample_story, "/repo")

        assert result is False

    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_cycle_in_tasks_returns_false(self, mock_plan, mock_llm, sample_story):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[
                Task("t1", "p1", "A", "D", TaskType.BACKEND, dependencies=["t2"]),
                Task("t2", "p1", "B", "D", TaskType.BACKEND, dependencies=["t1"]),
            ],
        )

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_story(sample_story, "/repo")

        assert result is False


class TestPlanOrchestratorMultiStory:
    @patch("execution.run_execution.ExecutionEngine.execute_task", return_value=True)
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_execute_stories_all_pass(self, mock_plan, mock_exec, mock_llm):
        mock_plan.return_value = ImplementationPlan(
            plan_id="p1",
            feature_title="F",
            feature_description="D",
            tasks=[Task("t1", "p1", "T", "D", TaskType.BACKEND)],
        )

        stories = [
            {"story_id": "S1", "title": "Story 1", "acceptance_criteria": []},
            {"story_id": "S2", "title": "Story 2", "acceptance_criteria": []},
        ]

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_stories(stories, "/repo")

        assert result is True
        assert mock_plan.call_count == 2

    @patch("execution.run_execution.ExecutionEngine.execute_task", return_value=True)
    @patch("planning.planner_agent.PlannerAgent.plan")
    def test_execute_stories_aborts_on_first_failure(self, mock_plan, mock_exec, mock_llm):
        # First story: plan fails
        mock_plan.return_value = None

        stories = [
            {"story_id": "S1", "title": "Story 1", "acceptance_criteria": []},
            {"story_id": "S2", "title": "Story 2", "acceptance_criteria": []},
        ]

        orch = PlanOrchestrator(mock_llm, None, workspace_root="/tmp/ws")
        result = orch.execute_stories(stories, "/repo")

        assert result is False
        assert mock_plan.call_count == 1  # Second story never attempted
