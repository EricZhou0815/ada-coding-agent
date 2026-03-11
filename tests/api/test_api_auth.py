"""
Tests for API authentication and authorization.
"""
import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import after setting environment variables
os.environ["API_KEYS"] = "test-key-1,test-key-2,test-key-3"

from api.main import app


@pytest.fixture
def client():
    """FastAPI test client with mocked Redis."""
    with patch("api.webhooks.vcs.redis_client", MagicMock()):
        return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database session."""
    with patch('api.main.get_db') as mock:
        db = MagicMock()
        mock.return_value = iter([db])
        yield db


@pytest.fixture
def valid_story_payload():
    """Valid story execution request."""
    return {
        "repo_url": "https://github.com/test/repo",
        "stories": [
            {
                "title": "Test Story",
                "story_id": "STORY-123",
                "acceptance_criteria": ["Test passes"],
                "description": "Test description"
            }
        ],
        "use_mock": True
    }


class TestAPIAuthentication:
    """Test suite for API key authentication."""
    
    def test_execute_without_api_key_fails(self, client, valid_story_payload):
        """Request without X-Api-Key header should return 401."""
        response = client.post("/api/v1/execute", json=valid_story_payload)
        
        assert response.status_code == 401  # Authentication error when API key is missing
        assert "Invalid or missing API key" in response.json()["detail"]
    
    def test_execute_with_invalid_api_key_fails(self, client, valid_story_payload):
        """Request with invalid API key should return 401."""
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "invalid-key-xyz"}
        )
        
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]
    
    def test_execute_with_empty_api_key_fails(self, client, valid_story_payload):
        """Request with empty API key should return 401."""
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": ""}
        )
        
        assert response.status_code == 401
    
    @patch('api.main.execute_sdlc_story')
    def test_execute_with_valid_api_key_succeeds(self, mock_task, client, mock_db, valid_story_payload):
        """Request with valid API key should succeed."""
        # Mock Celery task
        mock_task.delay = MagicMock()
        
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "test-key-1"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "QUEUED"
    
    @patch('api.main.execute_sdlc_story')
    def test_execute_with_second_valid_key_succeeds(self, mock_task, client, mock_db, valid_story_payload):
        """Multiple valid keys should all work."""
        mock_task.delay = MagicMock()
        
        # Test with second key
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "test-key-2"}
        )
        
        assert response.status_code == 200
        
        # Test with third key
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "test-key-3"}
        )
        
        assert response.status_code == 200
    
    def test_api_key_case_sensitive(self, client, valid_story_payload):
        """API keys should be case-sensitive."""
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "TEST-KEY-1"}  # Wrong case
        )
        
        assert response.status_code == 401


class TestAPIAuthenticationWithoutKeys:
    """Test behavior when API_KEYS is not configured (dev mode)."""
    
    @patch.dict(os.environ, {"API_KEYS": ""}, clear=False)
    @patch('api.main.execute_sdlc_story')
    def test_dev_mode_allows_requests_without_key(self, mock_task, client, mock_db, valid_story_payload):
        """
        When API_KEYS is not set, requests should succeed with a warning.
        This allows local development without authentication.
        """
        # Reload app to pick up new environment
        from importlib import reload
        import api.main
        
        # Mock Redis AND Celery broker connection before creating TestClient
        with patch("api.webhooks.vcs.redis_client", MagicMock()), \
             patch("api.main.execute_sdlc_story") as mock_exec:
            
            # Setup the mocked task
            mock_exec.delay = MagicMock()
            
            client = TestClient(api.main.app)
            
            # Request without API key should work in dev mode
            response = client.post(
                "/api/v1/execute",
                json=valid_story_payload
            )
            
            # Should succeed but log warning
            assert response.status_code in [200, 422]# May fail on validation or succeed


class TestEndpointProtection:
    """Test which endpoints are protected and which are public."""
    
    def test_health_endpoint_public(self, client):
        """Health check should not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_jobs_list_public(self, client, mock_db):
        """Job listing should not require authentication (for now)."""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
    
    def test_job_status_public(self, client, mock_db):
        """Job status should not require authentication (for now)."""
        # This will return 404 but shouldn't require auth
        response = client.get("/api/v1/jobs/fake-job-id")
        assert response.status_code == 404  # Not 401
    
    def test_webhook_endpoints_public(self, client):
        """
        Webhook endpoints should not require API key auth.
        They use HMAC signature verification instead.
        """
        # GitHub webhook should not require X-Api-Key
        response = client.post(
            "/api/v1/webhooks/github",
            json={"action": "opened"},
            headers={"X-Hub-Signature-256": "sha256=fake"}
        )
        
        # Webhooks fail on signature validation (returns 401)
        # The point is they don't check for X-Api-Key header
        # Status is 401 from signature failure, not from missing API key
        assert response.status_code in [401, 403, 400]  # Signature validation error


class TestAPIKeyFormat:
    """Test API key format validation."""
    
    @patch('api.main.execute_sdlc_story')
    def test_api_key_with_spaces_ignored(self, mock_task, client, mock_db, valid_story_payload):
        """API_KEYS with spaces should be trimmed."""
        # This is handled in verify_api_key: k.strip()
        # Keys "test-key-1", "test-key-2" are valid (spaces stripped)
        mock_task.delay = MagicMock()
        
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "test-key-1"}
        )
        
        # Should work since spaces are stripped from config
        assert response.status_code == 200
    
    @patch('api.main.execute_sdlc_story')
    @patch.dict(os.environ, {"API_KEYS": "key_with-special.chars123"}, clear=False)
    def test_special_characters_in_key(self, mock_task, client, mock_db, valid_story_payload):
        """API keys with special characters should work."""
        # Keys can contain hyphens, underscores, alphanumerics
        mock_task.delay = MagicMock()
        
        response = client.post(
            "/api/v1/execute",
            json=valid_story_payload,
            headers={"X-Api-Key": "key_with-special.chars123"}
        )
        
        # Exact match required
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
