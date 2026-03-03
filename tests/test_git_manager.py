"""
Tests for GitManager - git operations wrapper.
"""
import pytest
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from tools.git_manager import GitManager


class TestGitManagerInit:
    """Test GitManager initialization."""
    
    def test_init_with_path(self, tmp_path):
        """Should initialize with absolute path."""
        git_manager = GitManager(str(tmp_path))
        assert git_manager.repo_path == str(tmp_path.absolute())
    
    def test_init_converts_relative_path(self):
        """Should convert relative to absolute path."""
        git_manager = GitManager("./relative/path")
        assert os.path.isabs(git_manager.repo_path)


class TestGitManagerClone:
    """Test repository cloning."""
    
    @patch('subprocess.run')
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_clone_new_repo_success(self, mock_exists, mock_listdir, mock_run, tmp_path):
        """Should successfully clone a new repository."""
        mock_exists.return_value = False
        
        # Mock successful clone
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        
        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1] == "clone":
                return mock_result
            # Return successful result for set_git_identity calls
            return MagicMock(returncode=0, stdout="", stderr="")
        
        mock_run.side_effect = run_side_effect
        
        manager = GitManager.clone(
            "https://github.com/test/repo.git",
            str(tmp_path / "repo")
        )
        
        assert manager is not None
        assert isinstance(manager, GitManager)
        
        # Verify clone command was called
        clone_call = [c for c in mock_run.call_args_list if c[0][0][1] == "clone"]
        assert len(clone_call) > 0
    
    @patch('subprocess.run')
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_clone_with_github_token(self, mock_exists, mock_listdir, mock_run, tmp_path):
        """Should inject GitHub token into HTTPS URL."""
        mock_exists.return_value = False
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.return_value = mock_result
        
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}):
            manager = GitManager.clone(
                "https://github.com/test/repo.git",
                str(tmp_path / "repo")
            )
        
        # Verify token was injected in clone call
        clone_args = None
        for call_args in mock_run.call_args_list:
            if len(call_args[0]) > 0 and len(call_args[0][0]) > 1 and call_args[0][0][1] == "clone":
                clone_args = call_args[0][0]
                break
        
        assert clone_args is not None
        assert "x-access-token:ghp_test123@" in clone_args[2]
    
    @patch('subprocess.run')
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_clone_existing_directory_skips(self, mock_exists, mock_listdir, mock_run):
        """Should skip clone if directory exists and is non-empty."""
        mock_exists.return_value = True
        mock_listdir.return_value = ["file1.txt"]
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        manager = GitManager.clone(
            "https://github.com/test/repo.git",
            "/existing/path"
        )
        
        # Verify clone was NOT called (only set_git_identity)
        clone_calls = [c for c in mock_run.call_args_list if len(c[0][0]) > 1 and c[0][0][1] == "clone"]
        assert len(clone_calls) == 0
    
    @patch('subprocess.run')
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_clone_failure_raises_error(self, mock_exists, mock_listdir, mock_run):
        """Should raise RuntimeError on clone failure."""
        mock_exists.return_value = False
        
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: repository not found"
        mock_run.return_value = mock_result
        
        with pytest.raises(RuntimeError, match="git clone failed"):
            GitManager.clone("https://github.com/invalid/repo.git", "/tmp/test")


class TestGitManagerBranches:
    """Test branch operations."""
    
    @patch.object(GitManager, '_run')
    def test_current_branch(self, mock_run):
        """Should return current branch name."""
        mock_result = MagicMock()
        mock_result.stdout = "main\n"
        mock_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        branch = manager.current_branch()
        
        assert branch == "main"
        mock_run.assert_called_once_with(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    
    @patch.object(GitManager, '_run')
    def test_create_and_checkout_new_branch(self, mock_run):
        """Should create and checkout new branch."""
        # First call checks if branch exists (returns empty)
        # Second call creates and checks out
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),  # branch --list
            MagicMock(returncode=0)  # checkout -b
        ]
        
        manager = GitManager("/fake/path")
        manager.create_and_checkout_branch("feature-123")
        
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == ["git", "checkout", "-b", "feature-123"]
    
    @patch.object(GitManager, '_run')
    def test_create_existing_branch_checks_out(self, mock_run):
        """Should checkout existing branch instead of creating."""
        # First call shows branch exists
        # Second call checks out
        mock_run.side_effect = [
            MagicMock(stdout="  feature-123\n", returncode=0),  # branch --list
            MagicMock(returncode=0)  # checkout
        ]
        
        manager = GitManager("/fake/path")
        manager.create_and_checkout_branch("feature-123")
        
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == ["git", "checkout", "feature-123"]
    
    @patch.object(GitManager, '_run')
    def test_checkout_branch(self, mock_run):
        """Should checkout specified branch."""
        manager = GitManager("/fake/path")
        manager.checkout("develop")
        
        mock_run.assert_called_once_with(["git", "checkout", "develop"], check=True)


class TestGitManagerStatus:
    """Test status and diff operations."""
    
    @patch.object(GitManager, '_run')
    def test_has_changes_true(self, mock_run):
        """Should return True when changes exist."""
        mock_result = MagicMock()
        mock_result.stdout = " M file1.txt\nA  file2.txt\n"
        mock_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        assert manager.has_changes() is True
    
    @patch.object(GitManager, '_run')
    def test_has_changes_false(self, mock_run):
        """Should return False when no changes."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        assert manager.has_changes() is False
    
    @patch.object(GitManager, '_run')
    def test_changed_files_list(self, mock_run):
        """Should return list of changed files."""
        mock_result = MagicMock()
        mock_result.stdout = " M file1.txt\nA  file2.txt\n D file3.txt\n"
        mock_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        files = manager.changed_files()
        
        assert len(files) == 3
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "file3.txt" in files
    
    @patch.object(GitManager, '_run')
    def test_get_diff_summary_with_staged(self, mock_run):
        """Should return diff summary for staged changes."""
        def run_side_effect(cmd):
            if "--cached" in cmd:
                return MagicMock(stdout=" file1.txt | 10 +++++-----\n 1 file changed", returncode=0)
            else:
                return MagicMock(stdout="", returncode=0)
        
        mock_run.side_effect = run_side_effect
        
        manager = GitManager("/fake/path")
        summary = manager.get_diff_summary()
        
        assert "Staged:" in summary
        assert "file1.txt" in summary
    
    @patch.object(GitManager, '_run')
    def test_get_diff_summary_no_changes(self, mock_run):
        """Should return 'No changes' when nothing changed."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        
        manager = GitManager("/fake/path")
        summary = manager.get_diff_summary()
        
        assert summary == "No changes"


class TestGitManagerCommitPush:
    """Test commit and push operations."""
    
    @patch.object(GitManager, 'stage_all')
    @patch.object(GitManager, 'has_changes')
    @patch.object(GitManager, '_run')
    def test_commit_with_changes(self, mock_run, mock_has_changes, mock_stage):
        """Should commit when changes exist."""
        mock_has_changes.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        manager = GitManager("/fake/path")
        result = manager.commit("feat: add new feature")
        
        assert result is True
        mock_stage.assert_called_once()
        mock_run.assert_called_once_with(["git", "commit", "-m", "feat: add new feature"])
    
    @patch.object(GitManager, 'has_changes')
    def test_commit_without_changes_noop(self, mock_has_changes):
        """Should return False when nothing to commit."""
        mock_has_changes.return_value = False
        
        manager = GitManager("/fake/path")
        result = manager.commit("test message")
        
        assert result is False
    
    @patch.object(GitManager, 'stage_all')
    @patch.object(GitManager, 'has_changes')
    @patch.object(GitManager, '_run')
    def test_commit_failure_raises(self, mock_run, mock_has_changes, mock_stage):
        """Should raise RuntimeError on commit failure."""
        mock_has_changes.return_value = True
        mock_run.return_value = MagicMock(returncode=1, stderr="commit failed")
        
        manager = GitManager("/fake/path")
        
        with pytest.raises(RuntimeError, match="git commit failed"):
            manager.commit("test message")
    
    @patch.object(GitManager, '_run')
    def test_stage_all(self, mock_run):
        """Should stage all changes."""
        manager = GitManager("/fake/path")
        manager.stage_all()
        
        mock_run.assert_called_once_with(["git", "add", "."], check=True)
    
    @patch.object(GitManager, '_run')
    def test_push_success(self, mock_run):
        """Should push branch to remote."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        manager = GitManager("/fake/path")
        manager.push("feature-branch")
        
        mock_run.assert_called_once_with(
            ["git", "push", "--set-upstream", "origin", "feature-branch"]
        )
    
    @patch.object(GitManager, '_run')
    def test_push_with_custom_remote(self, mock_run):
        """Should push to custom remote."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        manager = GitManager("/fake/path")
        manager.push("feature-branch", remote="upstream")
        
        mock_run.assert_called_once_with(
            ["git", "push", "--set-upstream", "upstream", "feature-branch"]
        )
    
    @patch.object(GitManager, '_run')
    def test_push_failure_raises(self, mock_run):
        """Should raise RuntimeError on push failure."""
        mock_run.return_value = MagicMock(returncode=1, stderr="push rejected")
        
        manager = GitManager("/fake/path")
        
        with pytest.raises(RuntimeError, match="git push failed"):
            manager.push("feature-branch")
    
    @patch.object(GitManager, '_run')
    def test_pull_default(self, mock_run):
        """Should pull from origin/main by default."""
        manager = GitManager("/fake/path")
        manager.pull()
        
        mock_run.assert_called_once_with(["git", "pull", "origin", "main"], check=True)
    
    @patch.object(GitManager, '_run')
    def test_pull_custom_remote_branch(self, mock_run):
        """Should pull from custom remote and branch."""
        manager = GitManager("/fake/path")
        manager.pull(remote="upstream", branch="develop")
        
        mock_run.assert_called_once_with(["git", "pull", "upstream", "develop"], check=True)


class TestGitManagerIdentity:
    """Test git identity configuration."""
    
    @patch.object(GitManager, '_run')
    def test_set_git_identity_default(self, mock_run):
        """Should set default Ada identity."""
        manager = GitManager("/fake/path")
        manager.set_git_identity()
        
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0][0][0] == ["git", "config", "user.name", "Ada AI"]
        assert mock_run.call_args_list[1][0][0] == ["git", "config", "user.email", "ada@autonomous.ai"]
    
    @patch.object(GitManager, '_run')
    def test_set_git_identity_custom(self, mock_run):
        """Should set custom identity."""
        manager = GitManager("/fake/path")
        manager.set_git_identity(name="Test Bot", email="test@example.com")
        
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0][0][0] == ["git", "config", "user.name", "Test Bot"]
        assert mock_run.call_args_list[1][0][0] == ["git", "config", "user.email", "test@example.com"]


class TestGitManagerRun:
    """Test internal _run method."""
    
    @patch('subprocess.run')
    def test_run_success(self, mock_subprocess_run):
        """Should run git command successfully."""
        mock_result = MagicMock(returncode=0, stdout="output", stderr="")
        mock_subprocess_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        result = manager._run(["git", "status"])
        
        assert result.returncode == 0
        mock_subprocess_run.assert_called_once_with(
            ["git", "status"],
            capture_output=True,
            text=True,
            cwd=manager.repo_path
        )
    
    @patch('subprocess.run')
    def test_run_with_check_raises_on_failure(self, mock_subprocess_run):
        """Should raise RuntimeError when check=True and command fails."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error message")
        mock_subprocess_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        
        with pytest.raises(RuntimeError, match="Command failed"):
            manager._run(["git", "invalid"], check=True)
    
    @patch('subprocess.run')
    def test_run_without_check_returns_failure(self, mock_subprocess_run):
        """Should return result even on failure when check=False."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        mock_subprocess_run.return_value = mock_result
        
        manager = GitManager("/fake/path")
        result = manager._run(["git", "invalid"], check=False)
        
        assert result.returncode == 1


class TestGitManagerSlugify:
    """Test branch name slugification."""
    
    def test_slugify_basic(self):
        """Should convert text to slug."""
        slug = GitManager.slugify("As a user I want to reset my password")
        assert slug == "as-a-user-i-want-to-reset-my-password"
    
    def test_slugify_with_special_chars(self):
        """Should remove special characters."""
        slug = GitManager.slugify("Feature: Add @mentions & #hashtags!")
        assert slug == "feature-add-mentions-hashtags"
    
    def test_slugify_with_multiple_spaces(self):
        """Should collapse multiple spaces."""
        slug = GitManager.slugify("Too    many     spaces")
        assert slug == "too-many-spaces"
    
    def test_slugify_max_length(self):
        """Should respect max length."""
        long_text = "This is a very long title that exceeds the maximum length limit"
        slug = GitManager.slugify(long_text, max_len=20)
        assert len(slug) <= 20
        assert not slug.endswith("-")  # Should not end with hyphen
    
    def test_slugify_trim_hyphens(self):
        """Should trim leading/trailing hyphens."""
        slug = GitManager.slugify("---test---")
        assert slug == "test"
    
    def test_slugify_empty_string(self):
        """Should handle empty string."""
        slug = GitManager.slugify("")
        assert slug == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
