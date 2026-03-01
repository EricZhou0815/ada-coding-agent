import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
from api.main import app

client = TestClient(app)

def test_webhook_ignored_event():
    response = client.post(
        "/api/v1/webhooks/github",
        json={"repository": {"html_url": "url", "owner": {"login": "o"}, "name": "n"}},
        headers={"X-GitHub-Event": "ping"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

@patch("api.webhooks.vcs.fix_ci_failure.delay")
def test_workflow_run_failure(mock_task):
    payload = {
        "action": "completed",
        "workflow_run": {
            "conclusion": "failure",
            "head_branch": "ada/feat-1",
            "id": 123
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
        branch_name="ada/feat-1",
        run_id=123
    )

@patch("api.webhooks.vcs.apply_pr_feedback.delay")
def test_issue_comment_created(mock_task):
    payload = {
        "action": "created",
        "issue": {
            "number": 42,
            "pull_request": {}
        },
        "comment": {
            "body": "Optimize this!"
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
        feedback="Optimize this!"
    )
