"""
Extended tests for Config class to improve coverage.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from config import Config


class TestLLMProviderSelection:
    """Test LLM provider auto-detection logic."""
    
    def test_explicit_provider_takes_priority(self):
        """LLM_PROVIDER env var should override key-based detection."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "openai",
            "GROQ_API_KEY": "gsk_test",
            "OPENAI_API_KEY": ""
        }):
            assert Config.get_llm_provider() == "openai"
    
    def test_groq_selected_with_api_key(self):
        """Should select groq when GROQ_API_KEY is present."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "",
            "GROQ_API_KEY": "gsk_test123",
            "OPENAI_API_KEY": ""
        }, clear=False):
            assert Config.get_llm_provider() == "groq"
    
    def test_groq_selected_with_api_keys(self):
        """Should select groq when GROQ_API_KEYS is present."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "",
            "GROQ_API_KEYS": "gsk_1,gsk_2",
            "GROQ_API_KEY": "",
            "OPENAI_API_KEY": ""
        }, clear=False):
            assert Config.get_llm_provider() == "groq"
    
    def test_openai_selected_with_api_key(self):
        """Should select openai when OPENAI_API_KEY is present."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "",
            "GROQ_API_KEY": "",
            "OPENAI_API_KEY": "sk_test123"
        }, clear=False):
            assert Config.get_llm_provider() == "openai"
    
    def test_openai_selected_with_api_keys(self):
        """Should select openai when OPENAI_API_KEYS is present."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "",
            "GROQ_API_KEY": "",
            "OPENAI_API_KEYS": "sk_1,sk_2",
            "OPENAI_API_KEY": ""
        }, clear=False):
            assert Config.get_llm_provider() == "openai"
    
    def test_mock_fallback_no_keys(self):
        """Should fallback to mock when no API keys are present."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "",
            "GROQ_API_KEY": "",
            "GROQ_API_KEYS": "",
            "OPENAI_API_KEY": "",
            "OPENAI_API_KEYS": ""
        }, clear=False):
            assert Config.get_llm_provider() == "mock"
    
    def test_provider_case_insensitive(self):
        """LLM_PROVIDER should be case-insensitive."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "GROQ"}):
            assert Config.get_llm_provider() == "groq"


class TestLLMModel:
    """Test LLM model configuration."""
    
    def test_get_llm_model_from_env(self):
        """Should return model from LLM_MODEL env var."""
        with patch.dict(os.environ, {"LLM_MODEL": "llama-3.3-70b"}):
            assert Config.get_llm_model() == "llama-3.3-70b"
    
    def test_get_llm_model_none_when_not_set(self):
        """Should return None when LLM_MODEL not set."""
        # Remove LLM_MODEL from environment if it exists
        env = os.environ.copy()
        env.pop('LLM_MODEL', None)
        with patch.dict(os.environ, env, clear=True):
            result = Config.get_llm_model()
            assert result is None or result == ""


class TestAPIKeyPool:
    """Test API key pool creation for load balancing."""
    
    @patch('agents.api_key_pool.APIKeyPool')
    def test_groq_multi_key_pool(self, mock_pool_class):
        """Should create pool with multiple GROQ keys."""
        with patch.dict(os.environ, {
            "GROQ_API_KEYS": "gsk_1, gsk_2, gsk_3",
            "GROQ_API_KEY": ""
        }):
            pool = Config.get_api_key_pool("groq")
            
            mock_pool_class.assert_called_once()
            call_args = mock_pool_class.call_args[0][0]
            assert call_args == ["gsk_1", "gsk_2", "gsk_3"]
    
    @patch('agents.api_key_pool.APIKeyPool')
    def test_openai_multi_key_pool(self, mock_pool_class):
        """Should create pool with multiple OPENAI keys."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEYS": "sk_1,sk_2",
            "OPENAI_API_KEY": ""
        }):
            pool = Config.get_api_key_pool("openai")
            
            mock_pool_class.assert_called_once()
            call_args = mock_pool_class.call_args[0][0]
            assert call_args == ["sk_1", "sk_2"]
    
    @patch('agents.api_key_pool.APIKeyPool')
    def test_single_key_wrapped_in_pool(self, mock_pool_class):
        """Should wrap single key in pool for consistent interface."""
        with patch.dict(os.environ, {
            "GROQ_API_KEYS": "",
            "GROQ_API_KEY": "gsk_single"
        }):
            pool = Config.get_api_key_pool("groq")
            
            mock_pool_class.assert_called_once_with(["gsk_single"])
    
    @patch('agents.api_key_pool.APIKeyPool')
    def test_single_key_from_multi_var(self, mock_pool_class):
        """Should handle single key in multi-key variable."""
        with patch.dict(os.environ, {
            "GROQ_API_KEYS": "gsk_only_one",
            "GROQ_API_KEY": ""
        }):
            pool = Config.get_api_key_pool("groq")
            
            mock_pool_class.assert_called_once()
            call_args = mock_pool_class.call_args[0][0]
            assert call_args == ["gsk_only_one"]
    
    def test_unsupported_provider_returns_none(self):
        """Should return None for unsupported providers."""
        assert Config.get_api_key_pool("anthropic") is None
        assert Config.get_api_key_pool("unknown") is None
    
    def test_no_keys_returns_none(self):
        """Should return None when no keys are configured."""
        with patch.dict(os.environ, {
            "GROQ_API_KEYS": "",
            "GROQ_API_KEY": ""
        }, clear=False):
            assert Config.get_api_key_pool("groq") is None


class TestLLMClient:
    """Test LLM client instantiation."""
    
    @patch('agents.llm_client.LLMClient')
    @patch('config.Config.get_api_key_pool')
    def test_real_client_with_key_pool(self, mock_get_pool, mock_client_class):
        """Should pass key pool to LLMClient."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "LLM_MODEL": "llama-3"}):
            Config.get_llm_client()
            
            mock_client_class.assert_called_once_with(
                provider="groq",
                model="llama-3",
                key_pool=mock_pool
            )
    
    @patch('agents.llm_client.LLMClient')
    @patch('config.Config.get_api_key_pool')
    def test_real_client_without_key_pool(self, mock_get_pool, mock_client_class):
        """Should work when no key pool is available."""
        mock_get_pool.return_value = None
        
        # Clear LLM_MODEL to ensure test isolation
        env = {"LLM_PROVIDER": "openai"}
        if "LLM_MODEL" in os.environ:
            env["LLM_MODEL"] = ""
            
        with patch.dict(os.environ, env):
            Config.get_llm_client()
            
            # get_llm_model() might return "" instead of None when not set
            call_args = mock_client_class.call_args
            assert call_args[1]["provider"] == "openai"
            assert call_args[1]["key_pool"] is None
            # Model can be None or empty string when not set
            assert call_args[1]["model"] in (None, "")


class TestIsolationBackend:
    """Test isolation backend selection."""
    
    def test_default_isolation_backend_sandbox(self):
        """Should default to sandbox backend."""
        env = os.environ.copy()
        env.pop('ADA_ISOLATION_BACKEND', None)
        with patch.dict(os.environ, env, clear=True):
            assert Config.get_isolation_backend_type() == "sandbox"
    
    def test_docker_isolation_backend(self):
        """Should select docker backend when configured."""
        with patch.dict(os.environ, {"ADA_ISOLATION_BACKEND": "docker"}):
            assert Config.get_isolation_backend_type() == "docker"
    
    def test_ecs_isolation_backend(self):
        """Should select ECS backend when configured."""
        with patch.dict(os.environ, {"ADA_ISOLATION_BACKEND": "ecs"}):
            assert Config.get_isolation_backend_type() == "ecs"
    
    def test_backend_type_case_insensitive(self):
        """Backend type should be case-insensitive."""
        with patch.dict(os.environ, {"ADA_ISOLATION_BACKEND": "DOCKER"}):
            assert Config.get_isolation_backend_type() == "docker"
    
    @patch('isolation.docker_backend.DockerBackend')
    def test_get_docker_backend_instance(self, mock_backend):
        """Should instantiate DockerBackend."""
        with patch.dict(os.environ, {"ADA_ISOLATION_BACKEND": "docker"}):
            Config.get_isolation_backend()
            mock_backend.assert_called_once()

    
    @patch('isolation.sandbox.SandboxBackend')
    def test_get_sandbox_backend_instance(self, mock_backend):
        """Should instantiate SandboxBackend with workspace_root."""
        with patch.dict(os.environ, {"ADA_ISOLATION_BACKEND": "sandbox"}):
            Config.get_isolation_backend(workspace_root="/tmp/ada-workspace")
            mock_backend.assert_called_once_with(workspace_root="/tmp/ada-workspace")


class TestVCSPlatform:
    """Test VCS platform selection."""
    
    def test_default_vcs_platform_github(self):
        """Should default to github."""
        env = os.environ.copy()
        env.pop('VCS_PLATFORM', None)
        with patch.dict(os.environ, env, clear=True):
            assert Config.get_vcs_platform() == "github"
    
    def test_gitlab_vcs_platform(self):
        """Should select gitlab when configured."""
        with patch.dict(os.environ, {"VCS_PLATFORM": "gitlab"}):
            assert Config.get_vcs_platform() == "gitlab"
    
    def test_vcs_platform_case_insensitive(self):
        """VCS platform should be case-insensitive."""
        with patch.dict(os.environ, {"VCS_PLATFORM": "GITHUB"}):
            assert Config.get_vcs_platform() == "github"
    
    @patch('tools.vcs_client.VCSClientFactory.create')
    def test_get_vcs_client_github(self, mock_create):
        """Should create GitHub client via factory."""
        with patch.dict(os.environ, {"VCS_PLATFORM": "github"}):
            Config.get_vcs_client()
            mock_create.assert_called_once_with("github")
    
    @patch('tools.vcs_client.VCSClientFactory.create')
    def test_get_vcs_client_gitlab(self, mock_create):
        """Should create GitLab client via factory."""
        with patch.dict(os.environ, {"VCS_PLATFORM": "gitlab"}):
            Config.get_vcs_client()
            mock_create.assert_called_once_with("gitlab")


class TestAdaBranchManagement:
    """Test Ada branch management configuration."""
    
    def test_default_branch_prefix(self):
        """Should default to 'ada-ai/' prefix."""
        env = os.environ.copy()
        env.pop('ADA_BRANCH_PREFIX', None)
        with patch.dict(os.environ, env, clear=True):
            assert Config.get_ada_branch_prefix() == "ada-ai/"
    
    def test_custom_branch_prefix(self):
        """Should use custom branch prefix from env."""
        with patch.dict(os.environ, {"ADA_BRANCH_PREFIX": "bot/"}):
            assert Config.get_ada_branch_prefix() == "bot/"


class TestAppVersion:
    """Test application version configuration."""
    
    def test_default_app_version(self):
        """Should default to '1.0.0'."""
        env = os.environ.copy()
        env.pop('APP_VERSION', None)
        with patch.dict(os.environ, env, clear=True):
            assert Config.get_app_version() == "1.0.0"
    
    def test_custom_app_version(self):
        """Should use custom version from env."""
        with patch.dict(os.environ, {"APP_VERSION": "2.3.1"}):
            assert Config.get_app_version() == "2.3.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
