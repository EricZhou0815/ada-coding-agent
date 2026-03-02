import pytest
import os
import json
from unittest.mock import Mock, patch
from agents.coding_agent import CodingAgent
from agents.llm_client import LLMClient
from agents.base_agent import AgentResult

@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.get_conversation_history.return_value = [{"role": "user", "content": "hi"}]
    return llm

@pytest.fixture
def mock_tools():
    return Mock()

def test_coding_agent_checkpointing(mock_llm, mock_tools, tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    agent = CodingAgent(mock_llm, mock_tools)
    
    # Mock LLM to return a finish response immediately
    mock_llm.generate.return_value = {"content": "I am done. finish", "function_call": None}
    
    story = {"story_id": "RES-1", "title": "Test Story"}
    context = {"checkpoint_path": str(checkpoint_file)}
    
    agent.run(story, "/mock/repo", context)
    
    # Check if checkpoint was saved
    assert os.path.exists(checkpoint_file)
    with open(checkpoint_file, "r") as f:
        state = json.load(f)
        assert state["tool_call_count"] == 0
        assert state["messages"] == [{"role": "user", "content": "hi"}]

def test_coding_agent_resume(mock_llm, mock_tools, tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    
    # Pre-populate checkpoint
    previous_messages = [{"role": "user", "content": "previous step"}]
    with open(checkpoint_file, "w") as f:
        json.dump({"messages": previous_messages, "tool_call_count": 5}, f)
        
    agent = CodingAgent(mock_llm, mock_tools)
    mock_llm.generate.return_value = {"content": "finish", "function_call": None}
    
    story = {"story_id": "RES-1", "title": "Test Story"}
    context = {"checkpoint_path": str(checkpoint_file)}
    
    agent.run(story, "/mock/repo", context)
    
    # Verify set_conversation_history was called with previous messages
    mock_llm.set_conversation_history.assert_called_once_with(previous_messages)

@patch("time.sleep", return_value=None)
def test_llm_client_retries(mock_sleep):
    # Mock the client.chat.completions.create to fail twice then succeed
    mock_client_instance = Mock()
    mock_client_instance.chat.completions.create.side_effect = [
        Exception("Rate limit"),
        Exception("Server error"),
        Mock(choices=[Mock(message=Mock(content="Success", tool_calls=None))])
    ]
    
    with patch("agents.llm_client.OpenAI", return_value=mock_client_instance):
        client = LLMClient(api_key="test", provider="openai")
        client.generate("hello")
        
        assert mock_client_instance.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2
