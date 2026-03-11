"""
Unit tests for Planning Agent
"""

import json
import pytest
from unittest.mock import Mock, MagicMock
from agents.planning_agent import PlanningAgent, InteractionHandler
from agents.base_agent import AgentResult


class MockInteractionHandler(InteractionHandler):
    """Mock handler for testing that provides preset responses."""
    
    def __init__(self, responses=None):
        self.responses = responses or []
        self.response_index = 0
        self.questions_received = []
        self.messages_received = []
    
    def ask_question(self, question: str) -> str:
        self.questions_received.append(question)
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response
        return "No more responses"
    
    def show_message(self, message: str) -> None:
        self.messages_received.append(message)


class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self, responses=None):
        self.responses = responses or []
        self.response_index = 0
        self.conversation_history = []
        self.generate_calls = []
    
    def reset_conversation(self):
        self.conversation_history = []
    
    def generate(self, prompt, tools=None):
        self.generate_calls.append({"prompt": prompt, "tools": tools})
        
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            
            # Add to conversation history
            self.conversation_history.append({
                "role": "user",
                "content": prompt
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": response
            })
            
            return {
                "content": response,
                "function_call": None,
                "finish_reason": "stop"
            }
        
        # Default response
        return {
            "content": "How should users initiate this?",
            "function_call": None,
            "finish_reason": "stop"
        }


def test_planning_agent_initialization():
    """Test that Planning Agent initializes correctly."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm, max_iterations=5)
    
    assert agent.name == "Planner"
    assert agent.max_iterations == 5
    assert agent.llm == llm


def test_planning_agent_with_complete_story():
    """Test Planning Agent with an already complete story."""
    story_json = {
        "title": "As a user, I want to log in",
        "description": "Users sh should be able to log in with email and password",
        "acceptance_criteria": [
            "User can enter email and password",
            "System validates credentials",
            "User is redirected to dashboard on success"
        ]
    }
    
    # LLM immediately completes
    llm_response = f"""STORY_COMPLETE
```json
{json.dumps(story_json)}
```"""
    
    llm = MockLLMClient(responses=[llm_response])
    handler = MockInteractionHandler()
    agent = PlanningAgent(llm, max_iterations=5)
    
    result = agent.run(
        user_input=story_json,
        interaction_handler=handler,
        context={}
    )
    
    assert result.success
    assert "title" in result.output
    assert result.output["title"] == story_json["title"]
    assert "story_id" in result.output  # Auto-generated


def test_planning_agent_natural_language_input():
    """Test Planning Agent with natural language input."""
    
    # Simulate multi-turn conversation
    llm_responses = [
        "How should users request a password reset?",
        "How should they receive the reset link?",
        """STORY_COMPLETE
```json
{
  "title": "As a user, I want to reset my password",
  "description": "Users can request password reset via email",
  "acceptance_criteria": [
    "User can enter their email address",
    "System sends reset link via email",
    "Link expires after 1 hour"
  ]
}
```"""
    ]
    
    user_responses = [
        "By entering their email",
        "Via email with a link"
    ]
    
    llm = MockLLMClient(responses=llm_responses)
    handler = MockInteractionHandler(responses=user_responses)
    agent = PlanningAgent(llm, max_iterations=10)
    
    result = agent.run(
        user_input="I need password reset",
        interaction_handler=handler,
        context={}
    )
    
    assert result.success
    assert result.output["title"] == "As a user, I want to reset my password"
    assert len(result.output["acceptance_criteria"]) == 3
    
    # Check that questions were asked
    assert len(handler.questions_received) == 2


def test_planning_agent_max_iterations():
    """Test that Planning Agent stops at max iterations."""
    
    # LLM never completes, just keeps asking questions
    llm_responses = ["What is X?" for _ in range(15)]
    user_responses = ["Answer" for _ in range(15)]
    
    llm = MockLLMClient(responses=llm_responses)
    handler = MockInteractionHandler(responses=user_responses)
    agent = PlanningAgent(llm, max_iterations=5)
    
    result = agent.run(
        user_input="Build something",
        interaction_handler=handler,
        context={}
    )
    
    assert not result.success
    assert "max iterations" in result.output.lower()


def test_planning_agent_metadata():
    """Test that Planning Agent adds proper metadata to story."""
    
    story_json = {
        "title": "Test story",
        "description": "Test description",
        "acceptance_criteria": ["Criterion 1", "Criterion 2"]
    }
    
    llm_response = f"""STORY_COMPLETE
```json
{json.dumps(story_json)}
```"""
    
    llm = MockLLMClient(responses=[llm_response])
    handler = MockInteractionHandler()
    agent = PlanningAgent(llm, max_iterations=5)
    
    result = agent.run(
        user_input="Test input",
        interaction_handler=handler,
        context={}
    )
    
    assert result.success
    metadata = result.output.get("metadata", {})
    assert metadata["source"] == "planning_agent"
    assert metadata["planning_agent_version"] == "1.0"
    assert "planning_duration_seconds" in metadata
    assert "iterations" in metadata


def test_planning_agent_invalid_json():
    """Test Planning Agent handles invalid JSON gracefully."""
    
    llm_responses = [
        """STORY_COMPLETE
```json
{invalid json here
```""",
        """STORY_COMPLETE
```json
{
  "title": "Valid story",
  "description": "Valid description",
  "acceptance_criteria": ["Criterion 1"]
}
```"""
    ]
    
    llm = MockLLMClient(responses=llm_responses)
    handler = MockInteractionHandler(responses=["Retry"])
    agent = PlanningAgent(llm, max_iterations=10)
    
    result = agent.run(
        user_input="Test",
        interaction_handler=handler,
        context={}
    )
    
    # Should recover and succeed on second attempt
    assert result.success
    assert result.output["title"] == "Valid story"


def test_parse_input_string():
    """Test _parse_input with string input."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm)
    
    result = agent._parse_input("I need a login feature")
    assert isinstance(result, str)
    assert "I need a login feature" in result


def test_parse_input_complete_dict():
    """Test _parse_input with complete story dict."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm)
    
    story = {
        "title": "Test",
        "description": "Test desc",
        "acceptance_criteria": ["A", "B"]
    }
    
    result = agent._parse_input(story)
    assert "verify it's complete" in result.lower()
    assert "Test" in result


def test_parse_input_partial_dict():
    """Test _parse_input with partial story dict."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm)
    
    partial = {"title": "Test"}
    result = agent._parse_input(partial)
    assert "partial" in result.lower()


def test_extract_story_with_json_block():
    """Test story extraction from JSON code block."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm)
    
    content = """Here's the story:
```json
{
  "title": "Test",
  "description": "Desc",
  "acceptance_criteria": ["A"]
}
```"""
    
    story = agent._extract_story(content)
    assert story is not None
    assert story["title"] == "Test"


def test_extract_story_missing_fields():
    """Test story extraction fails with missing required fields."""
    llm = MockLLMClient()
    agent = PlanningAgent(llm)
    
    content = """```json
{
  "title": "Test"
}
```"""
    
    story = agent._extract_story(content)
    assert story is None  # Missing description and acceptance_criteria
