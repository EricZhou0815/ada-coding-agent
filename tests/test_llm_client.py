import pytest
import os
from unittest.mock import Mock, patch
from agents.llm_client import LLMClient

def test_init_missing_groq_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Groq API key not provided"):
            LLMClient(provider="groq")

def test_init_missing_openai_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="OpenAI API key not provided"):
            LLMClient(provider="openai")

def test_init_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported provider"):
        LLMClient(provider="fake_provider")

@patch("agents.llm_client.OpenAI")
def test_init_success(mock_openai):
    client = LLMClient(api_key="valid_key", provider="groq")
    assert client.api_key == "valid_key"
    assert client.provider == "groq"
    mock_openai.assert_called_once()
    
    # testing openai explicitly
    client2 = LLMClient(api_key="valid_key2", provider="openai")
    assert client2.api_key == "valid_key2"
    assert client2.provider == "openai"

@patch("agents.llm_client.OpenAI")
def test_reset_conversation(mock_openai):
    client = LLMClient(api_key="valid_key")
    client.conversation_history = [{"role": "user", "content": "hi"}]
    client.reset_conversation()
    assert client.conversation_history == []

@patch("agents.llm_client.OpenAI")
def test_generate(mock_openai):
    client = LLMClient(api_key="valid_key")
    
    # Mock response
    mock_choice = Mock()
    mock_choice.message.content = "hello there"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    client.client.chat.completions.create.return_value = mock_response
    
    result = client.generate("hello from user")
    assert result["content"] == "hello there"
    assert result["function_call"] is None
    assert result["finish_reason"] == "stop"
    
    # ensure history was updated
    assert client.conversation_history[0]["role"] == "user"
    assert client.conversation_history[0]["content"] == "hello from user"
    assert client.conversation_history[1]["role"] == "assistant"
    assert client.conversation_history[1]["content"] == "hello there"
