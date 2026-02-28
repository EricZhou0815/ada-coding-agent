import pytest
from unittest.mock import Mock, call
from orchestrator.task_executor import PipelineOrchestrator
from agents.base_agent import AgentResult

@pytest.fixture
def agent_1():
    agent = Mock()
    agent.name = "Agent1"
    agent.run = Mock()
    return agent

@pytest.fixture
def agent_2():
    agent = Mock()
    agent.name = "Agent2"
    agent.run = Mock()
    return agent

def test_pipeline_success_first_try(agent_1, agent_2):
    agent_1.run.return_value = AgentResult(success=True)
    agent_2.run.return_value = AgentResult(success=True)
    
    executor = PipelineOrchestrator([agent_1, agent_2], max_retries=3)
    
    task = {"task_id": "T1", "title": "Test Title"}
    completed_tasks = ["T0"]
    result = executor.execute_task(task, "/repo", completed_tasks)
    
    assert result is True
    # Verify task ID appended
    assert "T1" in completed_tasks
    # the mock records the final state of the list.
    agent_1.run.assert_called_once_with(task, "/repo", {
        "completed_tasks": ["T0", "T1"],
        "global_rules": []
    })
    agent_2.run.assert_called_once_with(task, "/repo", {
        "completed_tasks": ["T0", "T1"],
        "global_rules": []
    })

def test_pipeline_success_with_retries(agent_1, agent_2):
    # Agent 1 passes, Agent 2 fails first time but pushes feedback, passing on second try
    agent_1.run.return_value = AgentResult(success=True)
    agent_2.run.side_effect = [
        AgentResult(success=False, context_updates={"error": "Syntax Error!"}),
        AgentResult(success=True)
    ]
    
    executor = PipelineOrchestrator([agent_1, agent_2], max_retries=3)
    task = {"task_id": "T2", "title": "Retry Title"}
    
    result = executor.execute_task(task, "/repo", completed_tasks=[])
    
    assert result is True
    assert agent_1.run.call_count == 2
    assert agent_2.run.call_count == 2
    
    # Second time Agent 1 runs, the context should have the error pushed by Agent 2
    second_run_context = agent_1.run.call_args_list[1].args[2]
    assert second_run_context["error"] == "Syntax Error!"

def test_pipeline_max_retries(agent_1, agent_2):
    # Agent 1 always fails
    agent_1.run.return_value = AgentResult(success=False)
    
    executor = PipelineOrchestrator([agent_1, agent_2], max_retries=2)
    task = {"task_id": "T3", "title": "Impossible Title"}
    
    result = executor.execute_task(task, "/repo", completed_tasks=[])
    
    assert result is False
    assert agent_1.run.call_count == 2
    # Agent 2 should never be called because the pipeline breaks early
    assert agent_2.run.call_count == 0
