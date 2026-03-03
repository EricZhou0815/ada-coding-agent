import pytest
import os
import hmac
import hashlib
from unittest.mock import patch, Mock, MagicMock

# Set required environment variables for testing
os.environ["GITHUB_WEBHOOK_SECRET"] = "test_secret_key"
os.environ["VCS_PLATFORM"] = "github"
os.environ["GITHUB_TOKEN"] = "test_token"

# Skip if FastAPI not installed
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC signature for webhook payload"""
    mac = hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@patch("api.webhooks.vcs.verify_github_signature")
def test_webhook_ignored_event(mock_verify):
    """Test that ping events are ignored"""
    mock_verify.return_value = True
    
    response = client.post(
        "/api/v1/webhooks/github",
        json={"repository": {"html_url": "url", "owner": {"login": "o"}, "name": "n"}},
        headers={"X-GitHub-Event": "ping"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@patch("api.webhooks.vcs.verify_github_signature")
@patch("api.webhooks.vcs.fix_ci_failure.delay")
@patch("api.webhooks.vcs.Config.should_auto_fix_ci")
@patch("api.webhooks.vcs.Config.get_vcs_client")
def test_workflow_run_failure(mock_vcs, mock_should_fix, mock_task, mock_verify):
    """Test CI failure webhook triggers fix task"""
    mock_verify.return_value = True
    mock_should_fix.return_value = True  # Branch is in scope
    
    # Mock VCS client for PR comment
    mock_client = MagicMock()
    mock_vcs.return_value = mock_client
    
    payload = {
        "action": "completed",
        "workflow_run": {
            "conclusion": "failure",
            "head_branch": "ada-ai/feat-1",  # Updated prefix
            "id": 123,
            "name": "CI"
        },
        "repository": {
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "name": "repo"
        }
    }
    response = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "workflow_run"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    mock_task.assert_called_once_with(
        repo_url="https://github.com/owner/repo",
        owner="owner",
        repo="repo",
        branch_name="ada-ai/feat-1",  # Updated prefix
        run_id=123
    )


@patch("api.webhooks.vcs.verify_github_signature")
@patch("api.webhooks.vcs.apply_pr_feedback.delay")
@patch("api.webhooks.vcs.Config.should_handle_pr_comment")
@patch("api.webhooks.vcs.is_trusted_commenter")
@patch("api.webhooks.vcs.Config.get_vcs_client")
def test_issue_comment_created(mock_vcs, mock_trusted, mock_should_handle, mock_task, mock_verify):
    """Test PR comment with @ada-ai trigger"""
    mock_verify.return_value = True
    mock_should_handle.return_value = True  # Branch is in scope
    mock_trusted.return_value = True  # User is trusted
    
    # Mock VCS client
    mock_client = MagicMock()
    mock_vcs.return_value = mock_client
    
    payload = {
        "action": "created",
        "issue": {
            "number": 42,
            "pull_request": {
                "head": {"ref": "ada-ai/feature"}
            }
        },
        "comment": {
            "body": "@ada-ai Optimize this!",  # Added trigger
            "user": {"login": "developer"}
        },
        "repository": {
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "name": "repo"
        }
    }
    response = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "issue_comment"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    mock_task.assert_called_once_with(
        repo_url="https://github.com/owner/repo",
        owner="owner",
        repo="repo",
        pr_number=42,
        feedback="Optimize this!"  # Trigger removed from instruction
    )


@patch("api.webhooks.vcs.verify_github_signature")
def test_webhook_signature_verification_failure(mock_verify):
    """Test that invalid signatures are rejected"""
    mock_verify.return_value = False
    
    payload = {
        "repository": {
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "name": "repo"
        }
    }
    response = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "ping"}
    )
    assert response.status_code == 401


@patch("api.webhooks.vcs.verify_github_signature")
@patch("api.webhooks.vcs.Config.should_auto_fix_ci")
def test_workflow_run_failure_out_of_scope(mock_should_fix, mock_verify):
    """Test CI failure on non-Ada branch is ignored"""
    mock_verify.return_value = True
    mock_should_fix.return_value = False  # Branch not in scope
    
    payload = {
        "action": "completed",
        "workflow_run": {
            "conclusion": "failure",
            "head_branch": "feature/human-branch",  # Human branch
            "id": 456
        },
        "repository": {
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "name": "repo"
        }
    }
    response = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "workflow_run"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@patch("api.webhooks.vcs.verify_github_signature")
@patch("api.webhooks.vcs.Config.should_handle_pr_comment")
def test_pr_comment_without_trigger(mock_should_handle, mock_verify):
    """Test PR comment without @ada-ai trigger is ignored"""
    mock_verify.return_value = True
    mock_should_handle.return_value = True
    
    payload = {
        "action": "created",
        "issue": {
            "number": 42,
            "pull_request": {}
        },
        "comment": {
            "body": "This looks good!",  # No @ada-ai trigger
            "user": {"login": "developer"}
        },
        "repository": {
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "name": "repo"
        }
    }
    response = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "issue_comment"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert "not addressed to @ada-ai" in response.json()["reason"]
