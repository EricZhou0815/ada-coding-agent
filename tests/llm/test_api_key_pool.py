"""
tests/test_api_key_pool.py

Unit tests for the API Key Pool functionality.
"""

import pytest
import time
import os
from unittest.mock import patch, Mock

from agents.llm.api_key_pool import (
    APIKeyPool,
    APIKeyEntry,
    KeyStatus,
    is_rate_limit_error,
    is_quota_exhausted_error,
    is_invalid_key_error,
)


class TestAPIKeyEntry:
    """Tests for the APIKeyEntry dataclass."""
    
    def test_initial_state(self):
        entry = APIKeyEntry(key="test_key")
        assert entry.key == "test_key"
        assert entry.status == KeyStatus.HEALTHY
        assert entry.is_available()
    
    def test_mark_failed_with_cooldown(self):
        entry = APIKeyEntry(key="test_key")
        entry.mark_failed(KeyStatus.RATE_LIMITED, cooldown_seconds=1.0)
        
        assert entry.status == KeyStatus.RATE_LIMITED
        assert not entry.is_available()
        assert entry.failure_count == 1
        
        # Wait for cooldown
        time.sleep(1.1)
        assert entry.is_available()
    
    def test_mark_healthy_resets_failure_count(self):
        entry = APIKeyEntry(key="test_key")
        entry.mark_failed(KeyStatus.RATE_LIMITED, cooldown_seconds=0)
        entry.mark_failed(KeyStatus.RATE_LIMITED, cooldown_seconds=0)
        assert entry.failure_count == 2
        
        entry.mark_healthy()
        assert entry.failure_count == 0
        assert entry.status == KeyStatus.HEALTHY
    
    def test_invalid_key_never_available(self):
        entry = APIKeyEntry(key="test_key")
        entry.status = KeyStatus.INVALID
        assert not entry.is_available()


class TestAPIKeyPool:
    """Tests for the APIKeyPool class."""
    
    def test_init_with_keys(self):
        pool = APIKeyPool(["key1", "key2", "key3"])
        assert pool.total_key_count() == 3
        assert pool.available_key_count() == 3
    
    def test_init_empty_list_raises(self):
        with pytest.raises(ValueError, match="At least one API key is required"):
            APIKeyPool([])
    
    def test_init_filters_empty_strings(self):
        pool = APIKeyPool(["key1", "", "  ", "key2"])
        assert pool.total_key_count() == 2
    
    def test_init_all_empty_raises(self):
        with pytest.raises(ValueError, match="At least one non-empty API key is required"):
            APIKeyPool(["", "  ", ""])
    
    def test_from_env_comma_separated(self):
        with patch.dict(os.environ, {"TEST_KEYS": "key1,key2,key3"}):
            pool = APIKeyPool.from_env("TEST_KEYS")
            assert pool.total_key_count() == 3
    
    def test_from_env_with_fallback(self):
        with patch.dict(os.environ, {"SINGLE_KEY": "mykey"}, clear=True):
            pool = APIKeyPool.from_env("MULTI_KEYS", fallback_single_key_var="SINGLE_KEY")
            assert pool.total_key_count() == 1
            assert pool.get_key() == "mykey"
    
    def test_from_env_missing_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="No API keys found"):
                APIKeyPool.from_env("MISSING_VAR")
    
    def test_get_key_round_robin(self):
        pool = APIKeyPool(["key1", "key2", "key3"])
        
        # Should cycle through keys
        keys_seen = [pool.get_key() for _ in range(6)]
        assert keys_seen == ["key1", "key2", "key3", "key1", "key2", "key3"]
    
    def test_get_key_skips_unavailable(self):
        pool = APIKeyPool(["key1", "key2", "key3"])
        
        # Mark key1 as rate limited
        pool.mark_rate_limited("key1", cooldown_seconds=60)
        
        # Should skip key1
        keys_seen = [pool.get_key() for _ in range(4)]
        assert "key1" not in keys_seen
        assert set(keys_seen) == {"key2", "key3"}
    
    def test_get_key_all_exhausted_raises(self):
        pool = APIKeyPool(["key1", "key2"])
        
        pool.mark_rate_limited("key1", cooldown_seconds=60)
        pool.mark_rate_limited("key2", cooldown_seconds=60)
        
        with pytest.raises(RuntimeError, match="All API keys are exhausted"):
            pool.get_key()
    
    def test_mark_success_restores_health(self):
        pool = APIKeyPool(["key1"])
        pool.mark_rate_limited("key1", cooldown_seconds=60)
        
        # Verify it's not available
        status = pool.get_status_summary()
        assert status["rate_limited"] == 1
        
        # Mark success
        pool.mark_success("key1")
        assert pool.available_key_count() == 1
    
    def test_mark_invalid_permanent(self):
        pool = APIKeyPool(["key1", "key2"])
        pool.mark_invalid("key1")
        
        # key1 should never be returned
        for _ in range(10):
            assert pool.get_key() == "key2"
    
    def test_get_status_summary(self):
        pool = APIKeyPool(["key1", "key2", "key3"])
        pool.mark_rate_limited("key1", cooldown_seconds=60)
        pool.mark_quota_exhausted("key2", cooldown_seconds=60)
        
        summary = pool.get_status_summary()
        assert summary["healthy"] == 1
        assert summary["rate_limited"] == 1
        assert summary["quota_exhausted"] == 1
    
    def test_len(self):
        pool = APIKeyPool(["key1", "key2"])
        assert len(pool) == 2


class TestErrorClassifiers:
    """Tests for error classification functions."""
    
    def test_is_rate_limit_error(self):
        assert is_rate_limit_error(Exception("Rate limit exceeded"))
        assert is_rate_limit_error(Exception("429 Too Many Requests"))
        assert is_rate_limit_error(Exception("You've exceeded your RPM limit"))
        assert not is_rate_limit_error(Exception("Connection timeout"))
    
    def test_is_quota_exhausted_error(self):
        assert is_quota_exhausted_error(Exception("insufficient_quota"))
        assert is_quota_exhausted_error(Exception("You exceeded your current quota"))
        assert is_quota_exhausted_error(Exception("Billing issue detected"))
        assert not is_quota_exhausted_error(Exception("Rate limit exceeded"))
    
    def test_is_invalid_key_error(self):
        assert is_invalid_key_error(Exception("Invalid API key provided"))
        assert is_invalid_key_error(Exception("401 Unauthorized"))
        assert is_invalid_key_error(Exception("Authentication failed"))
        assert not is_invalid_key_error(Exception("Rate limit exceeded"))


class TestLLMClientKeyRotation:
    """Integration tests for LLMClient with key rotation."""
    
    @patch("agents.llm.llm_strategies.OpenAI")
    def test_client_with_key_pool(self, mock_openai):
        from agents.llm import LLMClient
        
        pool = APIKeyPool(["key1", "key2", "key3"])
        client = LLMClient(provider="groq", key_pool=pool)
        
        assert client._current_api_key in ["key1", "key2", "key3"]
        assert client.key_pool is pool
    
    @patch("agents.llm.llm_strategies.OpenAI")
    def test_rotate_key(self, mock_openai):
        from agents.llm import LLMClient
        
        pool = APIKeyPool(["key1", "key2"])
        client = LLMClient(provider="groq", key_pool=pool)
        
        first_key = client._current_api_key
        success = client._rotate_key()
        
        assert success
        # Should have rotated to a different key (or same if only one available)
        assert client._current_api_key in ["key1", "key2"]
    
    @patch("agents.llm.llm_strategies.OpenAI")
    def test_rotate_key_no_pool(self, mock_openai):
        from agents.llm import LLMClient
        
        client = LLMClient(api_key="single_key", provider="groq")
        success = client._rotate_key()
        
        assert not success  # No pool, can't rotate


class TestConfigKeyPool:
    """Tests for Config.get_api_key_pool()."""
    
    def test_get_api_key_pool_multi_keys(self):
        from config import Config
        
        with patch.dict(os.environ, {"GROQ_API_KEYS": "key1,key2,key3"}):
            pool = Config.get_api_key_pool("groq")
            assert pool is not None
            assert pool.total_key_count() == 3
    
    def test_get_api_key_pool_single_key_fallback(self):
        from config import Config
        
        with patch.dict(os.environ, {"GROQ_API_KEY": "single_key"}, clear=True):
            pool = Config.get_api_key_pool("groq")
            assert pool is not None
            assert pool.total_key_count() == 1
    
    def test_get_api_key_pool_no_keys(self):
        from config import Config
        
        with patch.dict(os.environ, {}, clear=True):
            pool = Config.get_api_key_pool("groq")
            assert pool is None
