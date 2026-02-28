import pytest
from unittest.mock import Mock, call
from orchestrator.task_executor import AtomicTaskExecutor

@pytest.fixture
def mock_coding_agent():
    agent = Mock()
    agent.run = Mock()
    return agent

@pytest.fixture
def mock_validation_agent():
    agent = Mock()
    agent.validate = Mock()
    return agent

def test_executor_success_first_try(mock_coding_agent, mock_validation_agent):
    mock_validation_agent.validate.return_value = {"passed": True, "feedback": []}
    
    executor = AtomicTaskExecutor(mock_coding_agent, mock_validation_agent, "/repo", max_iterations=3)
    
    task = {"task_id": "T1", "title": "Test Title"}
    result = executor.execute_task(task, ["T0"])
    
    assert result is True
    mock_coding_agent.run.assert_called_once_with(
        atomic_task=task,
        repo_path="/repo",
        completed_tasks=["T0"],
        validation_feedback=[]
    )
    mock_validation_agent.validate.assert_called_once_with("/repo")

def test_executor_success_with_retries(mock_coding_agent, mock_validation_agent):
    # Fails first, passes second
    mock_validation_agent.validate.side_effect = [
        {"passed": False, "feedback": ["Linter error on line 1"]},
        {"passed": True, "feedback": []}
    ]
    
    executor = AtomicTaskExecutor(mock_coding_agent, mock_validation_agent, "/repo", max_iterations=3)
    task = {"task_id": "T2", "title": "Retry Title"}
    
    result = executor.execute_task(task, [])
    
    assert result is True
    assert mock_coding_agent.run.call_count == 2
    assert mock_validation_agent.validate.call_count == 2
    
    # Check the feedback pushed to the second run
    second_run_kwargs = mock_coding_agent.run.call_args_list[1].kwargs
    assert second_run_kwargs["validation_feedback"] == ["Linter error on line 1"]

def test_executor_max_iterations(mock_coding_agent, mock_validation_agent):
    # Always fails
    mock_validation_agent.validate.return_value = {"passed": False, "feedback": ["Bad logic"]}
    
    executor = AtomicTaskExecutor(mock_coding_agent, mock_validation_agent, "/repo", max_iterations=2)
    task = {"task_id": "T3", "title": "Impossible Title"}
    
    with pytest.raises(RuntimeError, match="exceeded max iterations \\(2\\)"):
        executor.execute_task(task, [])
    
    assert mock_coding_agent.run.call_count == 2
    assert mock_validation_agent.validate.call_count == 2
