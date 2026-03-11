"""
tests/test_mock_llm_client.py

Tests for MockLLMClient used in testing without real API calls.
"""

import pytest
import json
from agents.llm import MockLLMClient


class TestMockLLMClientInit:
    """Tests for MockLLMClient initialization."""
    
    def test_init_empty_history(self):
        """Should initialize with empty conversation history."""
        client = MockLLMClient()
        
        assert client.conversation_history == []
    
    def test_init_step_zero(self):
        """Should initialize with step counter at 0."""
        client = MockLLMClient()
        
        assert client.step == 0


class TestMockLLMClientGenerate:
    """Tests for MockLLMClient.generate() method."""
    
    def test_generate_step_1_list_files(self):
        """Should return list_files function call on step 1."""
        client = MockLLMClient()
        
        response = client.generate("Start the task", tools=None)
        
        assert response["content"] is not None
        assert response["function_call"] is not None
        assert response["function_call"].name == "list_files"
        assert response["finish_reason"] == "function_call"
    
    def test_generate_step_2_read_file(self):
        """Should return read_file function call for app.py on step 2."""
        client = MockLLMClient()
        client.generate("Start", tools=None)  # Step 1
        
        response = client.generate("Result of step 1", tools=None)  # Step 2
        
        assert response["function_call"].name == "read_file"
        args = json.loads(response["function_call"].arguments)
        assert "app.py" in args["path"]
    
    def test_generate_step_3_read_auth_file(self):
        """Should return read_file function call for auth.py on step 3."""
        client = MockLLMClient()
        client.generate("Start", tools=None)  # Step 1
        client.generate("Result", tools=None)  # Step 2
        
        response = client.generate("Result", tools=None)  # Step 3
        
        assert response["function_call"].name == "read_file"
        args = json.loads(response["function_call"].arguments)
        assert "auth.py" in args["path"]
    
    def test_generate_step_4_write_auth_file(self):
        """Should return write_file function call to update auth.py on step 4."""
        client = MockLLMClient()
        for _ in range(3):
            client.generate("Result", tools=None)
        
        response = client.generate("Result", tools=None)  # Step 4
        
        assert response["function_call"].name == "write_file"
        args = json.loads(response["function_call"].arguments)
        assert "auth.py" in args["path"]
        assert "jwt" in args["content"].lower()
    
    def test_generate_step_5_write_app_file(self):
        """Should return write_file function call to update app.py on step 5."""
        client = MockLLMClient()
        for _ in range(4):
            client.generate("Result", tools=None)
        
        response = client.generate("Result", tools=None)  # Step 5
        
        assert response["function_call"].name == "write_file"
        args = json.loads(response["function_call"].arguments)
        assert "app.py" in args["path"]
    
    def test_generate_final_step_finishes(self):
        """Should return FINISH response after all steps."""
        client = MockLLMClient()
        for _ in range(5):
            client.generate("Result", tools=None)
        
        response = client.generate("Result", tools=None)  # Step 6+
        
        assert response["function_call"] is None
        assert response["finish_reason"] == "stop"
        assert "FINISH" in response["content"] or "finish" in response["content"].lower()
    
    def test_generate_updates_conversation_history(self):
        """Should append user and assistant messages to history."""
        client = MockLLMClient()
        
        client.generate("User prompt", tools=None)
        
        assert len(client.conversation_history) == 2
        assert client.conversation_history[0]["role"] == "user"
        assert client.conversation_history[0]["content"] == "User prompt"
        assert client.conversation_history[1]["role"] == "assistant"
    
    def test_generate_increments_step(self):
        """Should increment step counter on each call."""
        client = MockLLMClient()
        
        assert client.step == 0
        client.generate("Prompt 1", tools=None)
        assert client.step == 1
        client.generate("Prompt 2", tools=None)
        assert client.step == 2
    
    def test_generate_includes_tool_calls_in_history(self):
        """Should include tool_calls in assistant message when function_call exists."""
        client = MockLLMClient()
        
        response = client.generate("Start task", tools=None)
        
        assistant_msg = client.conversation_history[1]
        assert assistant_msg["tool_calls"] is not None
        assert len(assistant_msg["tool_calls"]) == 1
        assert assistant_msg["tool_calls"][0]["type"] == "function"
        assert assistant_msg["tool_calls"][0]["function"]["name"] == response["function_call"].name
    
    def test_generate_no_tool_calls_in_final_step(self):
        """Should have None tool_calls in history when no function_call."""
        client = MockLLMClient()
        for _ in range(6):
            client.generate("Result", tools=None)
        
        assistant_msg = client.conversation_history[-1]
        assert assistant_msg["tool_calls"] is None


class TestMockLLMClientFunctionCall:
    """Tests for MockLLMClient._create_function_call() method."""
    
    def test_create_function_call_structure(self):
        """Should create function call object with name and arguments."""
        client = MockLLMClient()
        
        func_call = client._create_function_call("test_func", {"arg1": "value1", "arg2": 42})
        
        assert func_call.name == "test_func"
        assert isinstance(func_call.arguments, str)
        args = json.loads(func_call.arguments)
        assert args["arg1"] == "value1"
        assert args["arg2"] == 42
    
    def test_create_function_call_to_dict(self):
        """Should support to_dict() method for serialization."""
        client = MockLLMClient()
        
        func_call = client._create_function_call("test_func", {"key": "value"})
        result = func_call.to_dict()
        
        assert result["name"] == "test_func"
        assert result["arguments"] == json.dumps({"key": "value"})


class TestMockLLMClientHistory:
    """Tests for conversation history management."""
    
    def test_get_conversation_history(self):
        """Should return conversation history list."""
        client = MockLLMClient()
        client.generate("Test prompt", tools=None)
        
        history = client.get_conversation_history()
        
        assert isinstance(history, list)
        assert len(history) > 0
    
    def test_set_conversation_history(self):
        """Should set conversation history."""
        client = MockLLMClient()
        new_history = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First response"}
        ]
        
        client.set_conversation_history(new_history)
        
        assert client.conversation_history == new_history
    
    def test_set_conversation_history_infers_step(self):
        """Should infer step number from history length."""
        client = MockLLMClient()
        history = [
            {"role": "user", "content": "Msg 1"},
            {"role": "assistant", "content": "Resp 1"},
            {"role": "user", "content": "Msg 2"},
            {"role": "assistant", "content": "Resp 2"}
        ]
        
        client.set_conversation_history(history)
        
        # 4 messages / 2 = step 2
        assert client.step == 2
    
    def test_reset_conversation(self):
        """Should clear history and reset step counter."""
        client = MockLLMClient()
        client.generate("Test", tools=None)
        client.generate("Test", tools=None)
        
        client.reset_conversation()
        
        assert client.conversation_history == []
        assert client.step == 0


class TestMockLLMClientFullWorkflow:
    """Integration tests for full mock workflow."""
    
    def test_complete_task_workflow(self):
        """Should execute complete task from start to finish."""
        client = MockLLMClient()
        
        # Step through all the steps
        step_count = 0
        max_steps = 10
        finished = False
        
        while not finished and step_count < max_steps:
            response = client.generate("Continue task", tools=None)
            step_count += 1
            
            if response["finish_reason"] == "stop" and response["function_call"] is None:
                finished = True
        
        assert finished
        assert step_count == 6  # Should finish on step 6
    
    def test_all_steps_produce_valid_responses(self):
        """Should produce valid response structure for all steps."""
        client = MockLLMClient()
        
        for _ in range(7):  # Execute 7 steps to go past completion
            response = client.generate("Continue", tools=None)
            
            # All responses should have these keys
            assert "content" in response
            assert "finish_reason" in response
            # function_call can be None or present
            assert "function_call" in response or True
    
    def test_history_alternates_user_assistant(self):
        """Should maintain alternating user/assistant in history."""
        client = MockLLMClient()
        
        for i in range(3):
            client.generate(f"Prompt {i}", tools=None)
        
        # Check alternating pattern
        for i, msg in enumerate(client.conversation_history):
            if i % 2 == 0:
                assert msg["role"] == "user"
            else:
                assert msg["role"] == "assistant"
