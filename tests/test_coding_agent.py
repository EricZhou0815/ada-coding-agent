import pytest
from unittest.mock import Mock, patch
from agents.coding_agent import CodingAgent

class MockFunctionCall:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.reset_conversation = Mock()
    return llm

@pytest.fixture
def mock_tools():
    tools = Mock()
    tools.dummy_tool = Mock(return_value="tool_success")
    return tools

def test_coding_agent_initialization(mock_llm, mock_tools):
    agent = CodingAgent(mock_llm, mock_tools)
    assert agent.llm == mock_llm
    assert agent.tools == mock_tools
    assert agent.finished == False

def test_execute_tool_success(mock_llm, mock_tools):
    agent = CodingAgent(mock_llm, mock_tools)
    function_call = MockFunctionCall("dummy_tool", '{"arg": "val"}')
    result = agent._execute_tool(function_call)
    
    assert result["success"] == True
    assert result["result"] == "tool_success"
    mock_tools.dummy_tool.assert_called_once_with(arg="val")

def test_execute_tool_unknown(mock_llm, mock_tools):
    agent = CodingAgent(mock_llm, mock_tools)
    del mock_tools.unknown_tool  # Make hasattr return False for this specific attribute
    function_call = MockFunctionCall("unknown_tool", '{}')
    result = agent._execute_tool(function_call)
    
    assert result["success"] == False
    assert "Unknown tool" in result["error"]

def test_build_prompt(mock_llm, mock_tools):
    agent = CodingAgent(mock_llm, mock_tools)
    task = {
        "title": "Test Title",
        "description": "Test Desc"
    }
    prompt = agent._build_prompt(task, "/repo", ["task1"], ["failed"], ["Rule 1"])
    assert "Test Title" in prompt
    assert "Test Desc" in prompt
    assert "/repo" in prompt
    assert "task1" in prompt
    assert "failed" in prompt
    assert "Rule 1" in prompt

def test_run_finishes_on_keyword(mock_llm, mock_tools):
    agent = CodingAgent(mock_llm, mock_tools)
    mock_llm.generate.return_value = {
        "content": "I am finish",
        "function_call": None
    }
    
    task = {"title": "T", "description": "D"}
    agent.run(task, "/repo", {"completed_tasks": []})
    
    assert agent.finished == True
    mock_llm.reset_conversation.assert_called_once()
    mock_llm.generate.assert_called_once()
