import pytest
from unittest.mock import Mock
import json
from agents.validation_agent import ValidationAgent

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

def test_validation_agent_init(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    assert agent.llm == mock_llm
    assert agent.tools == mock_tools

def test_validate_no_criteria(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    result = agent.run(story={}, repo_path="/repo/path", context={})
    assert result.success is True
    assert result.output == "No global quality rules specified."
    mock_llm.generate.assert_not_called()

def test_validate_success_pass(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    mock_llm.generate.return_value = {
        "content": "Everything looks good to me! PASS",
        "function_call": None
    }
    story = {"title": "T1", "description": "D1"}
    result = agent.run(story, "/repo/path", {"global_rules": ["ensure test coverage"]})
    assert result.success is True

def test_validate_failure(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    mock_llm.generate.return_value = {
        "content": "I noticed an issue. FAIL Please fix bug.",
        "function_call": None
    }
    story = {"title": "T1", "description": "D1"}
    result = agent.run(story, "/repo/path", {"global_rules": ["ensure test coverage"]})
    assert result.success is False
    assert "I noticed an issue" in result.output[0]

def test_validate_tool_call(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    # 1. Ask for a tool, 2. Provide PASS response
    mock_llm.generate.side_effect = [
        {"content": "", "function_call": MockFunctionCall("dummy_tool", '{"arg": "val"}')},
        {"content": "PASS", "function_call": None}
    ]
    story = {"title": "T1", "description": "D1"}
    result = agent.run(story, "/repo/path", {"global_rules": ["ensure test coverage"]})
    
    assert mock_tools.dummy_tool.call_count == 1
    assert result.success is True

def test_validate_max_iterations(mock_llm, mock_tools):
    agent = ValidationAgent(mock_llm, mock_tools)
    # Always returning a tool call
    mock_llm.generate.return_value = {"content": "", "function_call": MockFunctionCall("dummy_tool", '{"arg": "val"}')}
    
    story = {"title": "T1", "description": "D1"}
    result = agent.run(story, "/repo/path", {"global_rules": ["ensure test coverage"]})
    
    assert result.success is False
    assert "maximum iterations" in result.output[0]
    assert mock_tools.dummy_tool.call_count == 5
