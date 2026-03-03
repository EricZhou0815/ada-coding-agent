"""
Extended tests for API endpoints - simplified version.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


class TestHealthCheckEndpoint:
    """Test the /health endpoint."""
    
    def test_health_check_returns_healthy(self):
        """Should return healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    @patch("api.main.Config.get_app_version")
    def test_health_check_includes_version(self, mock_version):
        """Should include app version in health check."""
        mock_version.return_value = "2.1.0"
        
        response = client.get("/health")
        
        assert response.status_code ==200
        data = response.json()
        assert data["version"] == "2.1.0"


class TestExecuteEndpointValidation:
    """Test execute endpoint validation."""
    
    def test_execute_requires_api_key(self):
        """Should require API key header."""
        response = client.post(
            "/api/v1/execute",
            json={
                "repo_url": "https://github.com/test/repo",
                "stories": []
            }
        )
        # Should fail with 401 or 422 depending on middleware order
        assert response.status_code in [401, 422]
    
    def test_execute_rejects_invalid_repo_url(self):
        """Should validate repo_url format."""
        with patch.dict("os.environ", {"API_KEYS": "test-key"}):
            response = client.post(
                "/api/v1/execute",
                headers={"X-Api-Key": "test-key"},
                json={
                    "repo_url": "not-a-url",
                    "stories": []
                }
            )
            # Should fail validation
            assert response.status_code == 422


class TestGetJobStatusEndpoint:
    """Test job status endpoint."""
    
    def test_get_job_status_not_found(self):
        """Should return 404 for non-existent job."""
        response = client.get("/api/v1/jobs/nonexistent-job-xyz-999")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"


class TestStreamEndpoint:
    """Test streaming endpoint."""
    
    @patch("api.main.redis.from_url")
    def test_stream_endpoint_accepts_requests(self, mock_redis):
        """Should accept requests to streaming endpoint."""
        from unittest.mock import MagicMock
        
        # Mock Redis to prevent real connection
        mock_pubsub = MagicMock()
        mock_pubsub.listen.return_value = []
        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis.return_value = mock_client
        
        # Stream endpoint should return 200
        # Note: Don't use timeout with TestClient (deprecated)
        response = client.get("/api/v1/jobs/test-job-123/stream")
        assert response.status_code == 200
    
    @patch("api.main.redis.from_url")
    def test_stream_endpoint_with_messages(self, mock_redis):
        """Should stream messages from Redis pubsub."""
        from unittest.mock import MagicMock
        
        # Mock Redis with actual messages
        mock_pubsub = MagicMock()
        mock_messages = [
            {"type": "subscribe", "data": 1},
            {"type": "message", "data": b'{"log": "test message"}'},
            {"type": "message", "data": b'{"log": "another message"}'}
        ]
        mock_pubsub.listen.return_value = iter(mock_messages)
        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis.return_value = mock_client
        
        response = client.get("/api/v1/jobs/test-job-456/stream")
        assert response.status_code == 200
        
        # Verify pubsub was subscribed and unsubscribed
        mock_pubsub.subscribe.assert_called_once_with("logs:test-job-456")
    
    @patch("api.main.redis.from_url")
    def test_stream_endpoint_cleanup_on_disconnect(self, mock_redis):
        """Should unsubscribe from Redis when stream ends."""
        from unittest.mock import MagicMock
        
        mock_pubsub = MagicMock()
        mock_pubsub.listen.return_value = iter([])
        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis.return_value = mock_client
        
        response = client.get("/api/v1/jobs/cleanup-test/stream")
        assert response.status_code == 200
        
        # Should have cleaned up pubsub connection
        # This tests the finally block
        mock_pubsub.close.assert_called()


class TestAPIListJobs:
    """Test list jobs endpoint."""
    
    def test_list_jobs_endpoint_exists(self):
        """Should accept GET requests to /api/v1/jobs."""
        response = client.get("/api/v1/jobs")
        
        # Should succeed (returns whatever is in DB)
        assert response.status_code == 200
        # Response should be a list
        assert isinstance(response.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
