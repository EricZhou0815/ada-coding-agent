"""Tests for planning/planner_agent.py — ImplementationPlan generation from stories."""

import pytest
import json
from unittest.mock import Mock, MagicMock
from planning.planner_agent import PlannerAgent
from planning.models import ImplementationPlan, TaskType


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
        "title": "As a user, I want to reset my password",
        "description": "Allow users to reset their password via email verification.",
        "acceptance_criteria": [
            "User can request password reset",
            "Reset email is sent",
            "User can set new password via reset link",
        ],
    }


def _make_llm_response(plan_dict):
    """Create a mock LLM response that returns the plan JSON."""
    json_str = json.dumps(plan_dict, indent=2)
    return {"content": f"```json\n{json_str}\n```"}


class TestPlannerAgentPlan:
    def test_generates_valid_plan(self, mock_llm, sample_story):
        plan_data = {
            "feature_title": "Password Reset Feature",
            "feature_description": "Allow password reset via email",
            "success_criteria": ["reset works"],
            "tasks": [
                {
                    "task_id": "task_1",
                    "title": "Add reset_token column",
                    "description": "Add migration for reset_token",
                    "type": "database",
                    "dependencies": [],
                    "success_criteria": ["migration created"],
                },
                {
                    "task_id": "task_2",
                    "title": "Reset endpoint",
                    "description": "POST /reset-password",
                    "type": "api",
                    "dependencies": ["task_1"],
                    "success_criteria": ["endpoint returns 200"],
                },
            ],
        }
        mock_llm.generate = Mock(return_value=_make_llm_response(plan_data))

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is not None
        assert isinstance(plan, ImplementationPlan)
        assert plan.feature_title == "Password Reset Feature"
        assert len(plan.tasks) == 2
        assert plan.tasks[0].type == TaskType.DATABASE
        assert plan.tasks[1].dependencies == ["task_1"]

    def test_returns_none_on_invalid_json(self, mock_llm, sample_story):
        mock_llm.generate = Mock(return_value={"content": "This is not JSON"})

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is None

    def test_returns_none_on_missing_tasks(self, mock_llm, sample_story):
        mock_llm.generate = Mock(return_value=_make_llm_response({
            "feature_title": "Feature",
            "feature_description": "Desc",
            # no "tasks" key
        }))

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is None

    def test_returns_none_on_missing_task_fields(self, mock_llm, sample_story):
        mock_llm.generate = Mock(return_value=_make_llm_response({
            "feature_title": "Feature",
            "feature_description": "Desc",
            "tasks": [{"task_id": "t1"}],  # missing title, description, type
        }))

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is None

    def test_returns_none_on_exception(self, mock_llm, sample_story):
        mock_llm.generate = Mock(side_effect=Exception("LLM exploded"))

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is None

    def test_extracts_plan_without_code_fence(self, mock_llm, sample_story):
        plan_data = {
            "feature_title": "Simple Feature",
            "feature_description": "Desc",
            "tasks": [
                {"task_id": "t1", "title": "T", "description": "D", "type": "backend"},
            ],
        }
        # Return raw JSON without markdown code fence
        mock_llm.generate = Mock(return_value={"content": json.dumps(plan_data)})

        planner = PlannerAgent(mock_llm)
        plan = planner.plan(sample_story, "/repo")

        assert plan is not None
        assert plan.feature_title == "Simple Feature"


class TestPlannerAgentRun:
    def test_run_interface_delegates_to_plan(self, mock_llm, sample_story):
        plan_data = {
            "feature_title": "Via Run",
            "feature_description": "D",
            "tasks": [
                {"task_id": "t1", "title": "T", "description": "D", "type": "backend"},
            ],
        }
        mock_llm.generate = Mock(return_value=_make_llm_response(plan_data))

        planner = PlannerAgent(mock_llm)
        result = planner.run(sample_story, "/repo", {})

        assert result.success is True
        assert result.output["feature_title"] == "Via Run"

    def test_run_returns_failure_on_plan_failure(self, mock_llm, sample_story):
        mock_llm.generate = Mock(return_value={"content": "invalid"})

        planner = PlannerAgent(mock_llm)
        result = planner.run(sample_story, "/repo", {})

        assert result.success is False


class TestPlannerAgentPrompt:
    def test_prompt_includes_story_fields(self, mock_llm, sample_story):
        plan_data = {
            "feature_title": "F",
            "feature_description": "D",
            "tasks": [
                {"task_id": "t1", "title": "T", "description": "D", "type": "backend"},
            ],
        }
        mock_llm.generate = Mock(return_value=_make_llm_response(plan_data))

        planner = PlannerAgent(mock_llm)
        planner.plan(sample_story, "/repo")

        # Check that the prompt passed to generate contains story info
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0]
        assert "reset my password" in prompt.lower() or "password" in prompt.lower()
        assert "acceptance criteria" in prompt.lower() or "Acceptance Criteria" in prompt

    def test_prompt_includes_repo_context_when_provided(self, mock_llm, sample_story):
        plan_data = {
            "feature_title": "F",
            "feature_description": "D",
            "tasks": [
                {"task_id": "t1", "title": "T", "description": "D", "type": "backend"},
            ],
        }
        mock_llm.generate = Mock(return_value=_make_llm_response(plan_data))

        planner = PlannerAgent(mock_llm)
        planner.plan(sample_story, "/repo", context={"repo_summary": "Python FastAPI project"})

        prompt = mock_llm.generate.call_args[0][0]
        assert "Python FastAPI project" in prompt
