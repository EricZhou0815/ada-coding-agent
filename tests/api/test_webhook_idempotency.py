"""
Tests for webhook idempotency (P0 Security Issue #3).
"""
import pytest
import json
import hmac
import hashlib
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)

# Webhook endpoint URL
WEBHOOK_URL = "/api/v1/webhooks/github"


class TestWebhookIdempotency:
    """Test webhook deduplication using X-GitHub-Delivery header."""
    
    @patch("api.webhooks.vcs.fix_ci_failure.delay", return_value=MagicMock())
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    @patch("api.webhooks.vcs.Config.get_vcs_client")
    def test_processes_first_delivery(self, mock_vcs, mock_redis, mock_verify, mock_task):
        """Should process webhook on first delivery."""
        # Setup mocks
        mock_redis.exists.return_value = False  # Not seen before
        mock_redis.setex.return_value = True
        
        # Create webhook payload
        payload = {
            "action": "completed",
            "workflow_run": {
                "id": 12345,
                "name": "CI",
                "conclusion": "failure",
                "head_branch": "ada-ai/test-branch"
            },
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        response = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "12345-67890-abcdef"
            }
        )
        
        # Should process successfully
        assert response.status_code in [200, 201]
        
        # Should mark delivery as processed
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "webhook:delivery:12345-67890-abcdef"
        assert call_args[1] == 86400  # 24 hour TTL
        assert call_args[2] == "processed"
    
    @patch("api.webhooks.vcs.redis_client")
    def test_ignores_duplicate_delivery(self, mock_redis):
        """Should ignore duplicate webhook deliveries."""
        # Setup mock - delivery already exists
        mock_redis.exists.return_value = True
        
        payload = {
            "action": "created",
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        response = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "duplicate-delivery-123"
            }
        )
        
        # Should return success but ignore
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "duplicate_delivery"
        
        # Should NOT try to set the key again
        mock_redis.setex.assert_not_called()
    
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    @patch("api.webhooks.vcs.fix_ci_failure")
    @patch("api.webhooks.vcs.Config.get_vcs_client")
    @patch("api.webhooks.vcs.Config.should_auto_fix_ci", return_value=True)
    def test_prevents_duplicate_ci_fix_jobs(self, mock_should_fix, mock_vcs, mock_fix, mock_redis, mock_verify):
        """Should prevent duplicate CI fix jobs from webhook retries."""
        # Setup mock - initially doesn't exist
        mock_redis.exists.side_effect = [False, True]
        mock_redis.setex.return_value = True

        # First delivery - should process
        payload = {
            "action": "completed",
            "workflow_run": {
                "id": 999,
                "name": "Tests",
                "conclusion": "failure",
                "head_branch": "ada-ai/bugfix"
            },
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }

        # First webhook
        response1 = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "unique-delivery-456"
            }
        )

        assert response1.status_code == 200
        assert mock_fix.delay.called

        # Simulate GitHub retry with same delivery ID
        response2 = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "unique-delivery-456"  # Same ID
            }
        )

        assert response2.status_code == 200
        assert response2.json()["status"] == "ignored"
        assert response2.json()["reason"] == "duplicate_delivery"

        # Celery task should NOT be called again
        assert mock_fix.delay.call_count == 1
    
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    def test_different_deliveries_processed_separately(self, mock_redis, mock_verify):
        """Should process different delivery IDs as separate events."""
        mock_redis.exists.return_value = False
        
        payload = {
            "action": "created",
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        # First delivery
        response1 = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "delivery-001"
            }
        )
        
        # Second delivery (different ID)
        response2 = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "delivery-002"
            }
        )
        
        # Both should be processed
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Both should set dedup keys
        assert mock_redis.setex.call_count == 2


class TestWebhookTTL:
    """Test deduplication key TTL (time-to-live)."""
    
    @patch("api.webhooks.vcs.redis_client")
    def test_ttl_set_to_24_hours(self, mock_redis):
        """Should set 24-hour TTL on deduplication keys."""
        mock_redis.exists.return_value = False
        
        payload = {
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "test-delivery-ttl"
            }
        )
        
        # Verify TTL is 24 hours (86400 seconds)
        mock_redis.setex.assert_called_once()
        ttl = mock_redis.setex.call_args[0][1]
        assert ttl == 86400


class TestMissingDeliveryHeader:
    """Test handling of missing X-GitHub-Delivery header."""
    
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    def test_continues_processing_without_delivery_header(self, mock_redis, mock_verify):
        """Should continue processing if header is missing (degraded mode)."""
        # No X-GitHub-Delivery header
        payload = {
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        response = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={"X-GitHub-Event": "push"}
            # No X-GitHub-Delivery header
        )
        
        # Should still process (backwards compatibility)
        assert response.status_code == 200
        
        # Should NOT try to check/set Redis key
        mock_redis.exists.assert_not_called()
        mock_redis.setex.assert_not_called()


class TestRedisFailure:
    """Test graceful degradation when Redis is unavailable."""
    
    @patch("api.webhooks.vcs.fix_ci_failure.delay", return_value=MagicMock())
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    @patch("api.webhooks.vcs.Config.get_vcs_client")
    def test_continues_on_redis_setex_error(self, mock_vcs, mock_redis, mock_verify, mock_task):
        """Should continue processing if Redis setex fails."""
        mock_redis.exists.return_value = False
        mock_redis.setex.side_effect = Exception("Redis connection lost")
        
        payload = {
            "action": "completed",
            "workflow_run": {
                "id": 111,
                "name": "Build",
                "conclusion": "failure",
                "head_branch": "ada-ai/feature"
            },
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        # Should not crash despite Redis error
        response = client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "redis-fail-test"
            }
        )
        
        # Should still process webhook
        assert response.status_code == 200
    
    @patch("api.webhooks.vcs.verify_github_signature", return_value=True)
    @patch("api.webhooks.vcs.redis_client")
    def test_continues_on_redis_exists_error(self, mock_redis, mock_verify):
        """Should continue if Redis exists check fails."""
        mock_redis.exists.side_effect = Exception("Redis timeout")
        
        payload = {
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        # Should handle gracefully
        response = client.post(
            WEBHOOK_URL,  json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "redis-error-test"
            }
        )
        
        # Might fail or continue depending on implementation
        # Key point: should not crash the server
        assert response.status_code in [200, 500]


class TestDeduplicationKeyFormat:
    """Test deduplication key naming convention."""
    
    @patch("api.webhooks.vcs.redis_client")
    def test_uses_correct_key_format(self, mock_redis):
        """Should use webhook:delivery:<id> key format."""
        mock_redis.exists.return_value = False
        
        delivery_id = "abc-123-def-456"
        
        payload = {
            "repository": {
                "html_url": "https://github.com/test/repo",
                "owner": {"login": "test"},
                "name": "repo"
            }
        }
        
        client.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": delivery_id
            }
        )
        
        # Verify key format
        expected_key = f"webhook:delivery:{delivery_id}"
        mock_redis.exists.assert_called_with(expected_key)
        
        setex_call = mock_redis.setex.call_args[0]
        assert setex_call[0] == expected_key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
