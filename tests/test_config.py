import os
import pytest
from unittest.mock import patch
from config import Config
from agents.mock_llm_client import MockLLMClient
from agents.llm_client import LLMClient

def test_get_llm_provider_explicit_env():
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}):
        assert Config.get_llm_provider() == "openai"
        
    with patch.dict(os.environ, {"LLM_PROVIDER": "Groq"}):
        assert Config.get_llm_provider() == "groq"

def test_get_llm_provider_fallback_groq():
    with patch.dict(os.environ, {"GROQ_API_KEY": "fake_key"}, clear=True):
        assert Config.get_llm_provider() == "groq"

def test_get_llm_provider_fallback_openai():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "fake_key"}, clear=True):
        assert Config.get_llm_provider() == "openai"

def test_get_llm_provider_fallback_mock():
    with patch.dict(os.environ, {}, clear=True):
        assert Config.get_llm_provider() == "mock"

def test_get_llm_client_mock():
    client = Config.get_llm_client(force_mock=True)
    assert isinstance(client, MockLLMClient)

@patch("config.Config.get_llm_provider", return_value="mock")
def test_get_llm_client_provider_mock(mock_provider):
    client = Config.get_llm_client()
    assert isinstance(client, MockLLMClient)

@patch("config.Config.get_llm_provider", return_value="openai")
def test_get_llm_client_openai(mock_provider):
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        client = Config.get_llm_client()
        assert isinstance(client, LLMClient)
        assert client.provider == "openai"
