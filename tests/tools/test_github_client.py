import pytest
from unittest.mock import patch, MagicMock
from tools.github_client import GitHubClient

@pytest.fixture
def gh():
    with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'}):
        return GitHubClient()

@patch('urllib.request.urlopen')
def test_create_issue_comment(mock_urlopen, gh):
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"id": 123, "body": "test comment"}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = gh.create_issue_comment("owner", "repo", 1, "hello")
    
    assert result["id"] == 123
    assert mock_urlopen.call_count == 1
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.get_method() == "POST"
    assert "/repos/owner/repo/issues/1/comments" in req.full_url

@patch('urllib.request.urlopen')
def test_get_job_logs(mock_urlopen, gh):
    mock_response = MagicMock()
    mock_response.read.return_value = b"log output"
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = gh.get_job_logs("owner", "repo", 456)
    
    assert result == "log output"
    assert "/repos/owner/repo/actions/jobs/456/logs" in mock_urlopen.call_args[0][0].full_url

def test_parse_repo_url():
    owner, repo = GitHubClient.parse_repo_url("https://github.com/abc/def")
    assert owner == "abc"
    assert repo == "def"
    
    owner, repo = GitHubClient.parse_repo_url("git@github.com:foo/bar.git")
    assert owner == "foo"
    assert repo == "bar"
