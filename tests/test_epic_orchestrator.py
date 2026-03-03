import pytest
import os
from unittest.mock import Mock, patch
from orchestrator.epic_orchestrator import EpicOrchestrator

@pytest.fixture
def mock_llm():
    return Mock()

@pytest.fixture
def mock_tools():
    return Mock()

@patch("config.Config.get_isolation_backend")
def test_execute_stories_success(mock_get_backend, mock_llm, mock_tools):
    # Setup mock sandbox
    mock_sandbox = Mock()
    mock_get_backend.return_value = mock_sandbox
    mock_sandbox.execute.return_value = True
    mock_sandbox.get_name.return_value = "MockBackend"
    
    orchestrator = EpicOrchestrator(mock_llm, mock_tools)
    stories = [{"story_id": "STORY-1", "title": "Title"}]
    
    success = orchestrator.execute_stories(stories, "/mock/repo")
    
    assert success is True
    mock_sandbox.setup.assert_called_once()
    mock_sandbox.execute.assert_called_once_with(stories[0], "/mock/repo")
    mock_sandbox.cleanup.assert_called_once()

@patch("config.Config.get_isolation_backend")
def test_execute_stories_failure(mock_get_backend, mock_llm, mock_tools):
    mock_sandbox = Mock()
    mock_get_backend.return_value = mock_sandbox
    mock_sandbox.execute.return_value = False
    mock_sandbox.get_name.return_value = "MockBackend"
    
    orchestrator = EpicOrchestrator(mock_llm, mock_tools)
    stories = [{"story_id": "FAIL-1", "title": "Fail"}]
    
    success = orchestrator.execute_stories(stories, "/mock/repo")
    
    assert success is False
    assert mock_sandbox.execute.call_count == 1
