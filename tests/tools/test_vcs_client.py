"""
tests/test_vcs_client.py

Tests for VCS client abstract interface and factory.
"""

import pytest
from tools.vcs_client import VCSClient, VCSClientFactory
from unittest.mock import patch, MagicMock


class TestVCSClientFactory:
    """Tests for VCSClientFactory."""
    
    def setup_method(self):
        """Reset the factory before each test."""
        VCSClientFactory._clients = {}
    
    def test_register_client(self):
        """Should register a VCS client implementation."""
        mock_client_class = MagicMock(spec=VCSClient)
        VCSClientFactory.register("testplatform", mock_client_class)
        
        assert "testplatform" in VCSClientFactory._clients
        assert VCSClientFactory._clients["testplatform"] == mock_client_class
    
    def test_register_case_insensitive(self):
        """Should store platform names in lowercase."""
        mock_client_class = MagicMock(spec=VCSClient)
        VCSClientFactory.register("GitHub", mock_client_class)
        
        assert "github" in VCSClientFactory._clients
    
    def test_create_with_registered_platform(self):
        """Should create instance of registered platform."""
        mock_client_class = MagicMock(spec=VCSClient)
        mock_instance = MagicMock(spec=VCSClient)
        mock_client_class.return_value = mock_instance
        
        VCSClientFactory.register("testplatform", mock_client_class)
        
        result = VCSClientFactory.create("testplatform", api_key="test_key")
        
        assert result == mock_instance
        mock_client_class.assert_called_once_with(api_key="test_key")
    
    def test_create_with_env_default(self):
        """Should use VCS_PLATFORM env var when platform not specified."""
        mock_client_class = MagicMock(spec=VCSClient)
        mock_instance = MagicMock(spec=VCSClient)
        mock_client_class.return_value = mock_instance
        
        VCSClientFactory.register("gitlab", mock_client_class)
        
        with patch.dict('os.environ', {'VCS_PLATFORM': 'gitlab'}):
            result = VCSClientFactory.create()
        
        assert result == mock_instance
    
    def test_create_defaults_to_github(self):
        """Should default to github when no env var set."""
        mock_client_class = MagicMock(spec=VCSClient)
        mock_instance = MagicMock(spec=VCSClient)
        mock_client_class.return_value = mock_instance
        
        VCSClientFactory.register("github", mock_client_class)
        
        with patch.dict('os.environ', {}, clear=True):
            result = VCSClientFactory.create()
        
        assert result == mock_instance
    
    def test_create_case_insensitive(self):
        """Should handle platform parameter case-insensitively."""
        mock_client_class = MagicMock(spec=VCSClient)
        mock_instance = MagicMock(spec=VCSClient)
        mock_client_class.return_value = mock_instance
        
        VCSClientFactory.register("github", mock_client_class)
        
        result = VCSClientFactory.create("GitHub")
        
        assert result == mock_instance
    
    def test_create_unknown_platform_raises(self):
        """Should raise ValueError for unknown platform."""
        VCSClientFactory.register("github", MagicMock())
        
        with pytest.raises(ValueError, match="Unknown VCS platform: 'unknown'"):
            VCSClientFactory.create("unknown")
    
    def test_create_shows_available_platforms_in_error(self):
        """Should list available platforms in error message."""
        VCSClientFactory.register("github", MagicMock())
        VCSClientFactory.register("gitlab", MagicMock())
        
        with pytest.raises(ValueError, match="Available platforms:"):
            VCSClientFactory.create("bitbucket")
    
    def test_available_platforms(self):
        """Should return list of registered platform names."""
        VCSClientFactory.register("github", MagicMock())
        VCSClientFactory.register("gitlab", MagicMock())
        
        platforms = VCSClientFactory.available_platforms()
        
        assert set(platforms) == {"github", "gitlab"}
    
    def test_available_platforms_empty(self):
        """Should return empty list when no platforms registered."""
        platforms = VCSClientFactory.available_platforms()
        
        assert platforms == []


class TestVCSClientAbstract:
    """Tests for VCSClient abstract base class."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Should not allow instantiation of abstract VCSClient."""
        with pytest.raises(TypeError):
            VCSClient()
    
    def test_subclass_must_implement_create_pull_request(self):
        """Should require implementation of create_pull_request."""
        class IncompleteClient(VCSClient):
            def get_pull_requests(self, owner, repo, state="open"):
                pass
            def get_pull_request(self, owner, repo, pr_number):
                pass
            def create_issue_comment(self, owner, repo, issue_number, body):
                pass
            def get_pipeline_jobs(self, owner, repo, pipeline_id):
                pass
            def get_job_logs(self, owner, repo, job_id):
                pass
            def is_collaborator(self, owner, repo, username):
                pass
            @staticmethod
            def parse_repo_url(url):
                pass
            @staticmethod
            def get_platform_name():
                pass
        
        with pytest.raises(TypeError):
            IncompleteClient()
    
    def test_concrete_implementation_can_be_created(self):
        """Should allow instantiation of complete implementation."""
        class ConcreteClient(VCSClient):
            def create_pull_request(self, owner, repo, head_branch, base_branch, title, body, draft=False):
                return {}
            def get_pull_requests(self, owner, repo, state="open"):
                return []
            def get_pull_request(self, owner, repo, pr_number):
                return {}
            def create_issue_comment(self, owner, repo, issue_number, body):
                return {}
            def get_pipeline_jobs(self, owner, repo, pipeline_id):
                return {}
            def get_job_logs(self, owner, repo, job_id):
                return ""
            def is_collaborator(self, owner, repo, username):
                return False
            @staticmethod
            def parse_repo_url(url):
                return ("owner", "repo")
            @staticmethod
            def get_platform_name():
                return "test"
        
        client = ConcreteClient()
        
        assert isinstance(client, VCSClient)
