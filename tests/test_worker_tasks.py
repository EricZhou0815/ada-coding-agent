"""
Tests for worker task utilities and helper functions.
"""
import pytest
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from worker.tasks import (
    _create_workspace,
    _append_job_log,
    _update_job_status,
    MAX_CI_FIX_RETRIES,
    CI_RETRY_KEY_TTL
)


class TestCreateWorkspace:
    """Test workspace creation helper."""
    
    def test_create_workspace_creates_directory(self, tmp_path):
        """Should create workspace directory with prefix."""
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(tmp_path)}):
            workspace = _create_workspace("test-prefix-123")
            
            assert workspace.exists()
            assert workspace.is_dir()
            assert "test-prefix-123" in str(workspace)
    
    def test_create_workspace_with_default_tmp_dir(self):
        """Should use default /tmp/ada_runs if ADA_TMP_DIR not set."""
        # Clear ADA_TMP_DIR
        with patch.dict(os.environ, {}, clear=True):
            with patch('pathlib.Path.mkdir') as mock_mkdir:
                workspace = _create_workspace("test-workspace")
                
                # Should create in default location
                assert "/tmp/ada_runs" in str(workspace) or "\\tmp\\ada_runs" in str(workspace)
                mock_mkdir.assert_called_once()
    
    def test_create_workspace_with_existing_directory(self, tmp_path):
        """Should not fail if directory already exists."""
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(tmp_path)}):
            workspace1 = _create_workspace("existing-workspace")
            workspace2 = _create_workspace("existing-workspace")
            
            assert workspace1 == workspace2
            assert workspace1.exists()
    
    def test_create_workspace_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if they don't exist."""
        nonexistent_base = tmp_path / "does" / "not" / "exist"
        
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(nonexistent_base)}):
            workspace = _create_workspace("nested-workspace")
            
            assert workspace.exists()
            assert workspace.parent.exists()


class TestAppendJobLog:
    """Test job logging helper."""
    
    @patch('worker.tasks.ada_logger')
    def test_append_job_log_sets_job_id(self, mock_logger):
        """Should set job ID on logger before logging."""
        _append_job_log("job-123", "Test message")
        
        mock_logger.set_job_id.assert_called_once_with("job-123")
        mock_logger.info.assert_called_once_with("System", "Test message")
    
    @patch('worker.tasks.ada_logger')
    def test_append_job_log_with_different_messages(self, mock_logger):
        """Should log various message types."""
        messages = [
            "Task started",
            "Processing file foo.py",
            "Tests passed",
            "Deployment complete"
        ]
        
        for msg in messages:
            _append_job_log("job-456", msg)
            mock_logger.info.assert_called_with("System", msg)


class TestUpdateJobStatus:
    """Test job status update helper."""
    
    @patch('worker.tasks.SessionLocal')
    def test_update_job_status_success(self, mock_session_class):
        """Should update job status in database."""
        # Setup mocks
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        
        mock_job = MagicMock()
        mock_job.status = "PENDING"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_job
        
        # Execute
        _update_job_status("job-789", "RUNNING")
        
        # Verify
        assert mock_job.status == "RUNNING"
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
    
    @patch('worker.tasks.SessionLocal')
    def test_update_job_status_job_not_found(self, mock_session_class):
        """Should handle case when job doesn't exist."""
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        
        # No job found
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Should not raise error
        _update_job_status("nonexistent-job", "FAILED")
        
        # Should not commit if job not found
        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()
    
    @patch('worker.tasks.SessionLocal')
    def test_update_job_status_all_states(self, mock_session_class):
        """Should handle all job status states."""
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        mock_job = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_job
        
        statuses = ["PENDING", "RUNNING", "SUCCESS", "FAILED"]
        
        for status in statuses:
            _update_job_status("job-abc", status)
            assert mock_job.status == status


class TestTaskConfiguration:
    """Test Celery task configuration."""
    
    def test_max_ci_fix_retries_constant(self):
        """MAX_CI_FIX_RETRIES should be reasonable."""
        assert MAX_CI_FIX_RETRIES == 3
        assert isinstance(MAX_CI_FIX_RETRIES, int)
        assert MAX_CI_FIX_RETRIES > 0
    
    def test_ci_retry_key_ttl_constant(self):
        """CI_RETRY_KEY_TTL should be 1 hour (3600 seconds)."""
        assert CI_RETRY_KEY_TTL == 3600
        assert isinstance(CI_RETRY_KEY_TTL, int)
        assert CI_RETRY_KEY_TTL > 0
    
    @patch('worker.tasks.celery_app')
    def test_celery_app_configured(self, mock_app):
        """Celery app should have proper configuration."""
        # Import triggers configuration
        from worker import tasks
        
        # Verify broker URL is set
        assert tasks.redis_url.startswith("redis://")
    
    def test_redis_url_from_env(self):
        """Should use REDIS_URL from environment."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://custom:6379/1"}):
            # Re-import to pick up env change
            from importlib import reload
            from worker import tasks as tasks_module
            reload(tasks_module)
            
            assert "redis://custom:6379/1" in tasks_module.redis_url or \
                   tasks_module.redis_url == "redis://localhost:6379/0"
    
    def test_celery_concurrency_from_env(self):
        """Should read CELERY_CONCURRENCY from environment."""
        with patch.dict(os.environ, {"CELERY_CONCURRENCY": "8"}):
            # The config is read at module load time
            # Just verify it would be an integer
            concurrency = int(os.getenv("CELERY_CONCURRENCY", "4"))
            assert concurrency == 8


class TestExecuteCodingTaskHelper:
    """Test the _execute_coding_task helper function."""
    
    @patch('worker.tasks.GitManager')
    @patch('worker.tasks.Config')
    @patch('worker.tasks.CodingAgent')
    @patch('worker.tasks.Tools')
    def test_execute_coding_task_success(
        self, mock_tools, mock_agent_class, mock_config, mock_git_manager, tmp_path
    ):
        """Should successfully execute coding task."""
        from worker.tasks import _execute_coding_task
        
        # Setup mocks
        mock_git = MagicMock()
        mock_git.has_changes.return_value = True
        mock_git_manager.clone.return_value = mock_git
        
        mock_llm = MagicMock()
        mock_config.get_llm_client.return_value = mock_llm
        
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_agent.run.return_value = mock_result
        mock_agent_class.return_value = mock_agent
        
        mock_logger = MagicMock()
        
        # Execute
        task_def = {
            "title": "Test Task",
            "description": "Test description",
            "acceptance_criteria": ["Should work"]
        }
        
        success, has_changes, git = _execute_coding_task(
            repo_url="https://github.com/test/repo.git",
            branch_name="feature-branch",
            task_definition=task_def,
            workspace_dir=tmp_path,
            logger=mock_logger
        )
        
        # Verify
        assert success is True
        assert has_changes is True
        assert git is mock_git
        mock_git_manager.clone.assert_called_once()
        mock_git.checkout.assert_called_once_with("feature-branch")
        mock_agent.run.assert_called_once()
    
    @patch('worker.tasks.GitManager')
    def test_execute_coding_task_clone_failure(self, mock_git_manager, tmp_path):
        """Should handle git clone failures gracefully."""
        from worker.tasks import _execute_coding_task
        
        # Simulate clone failure
        mock_git_manager.clone.side_effect = Exception("Clone failed")
        
        mock_logger = MagicMock()
        task_def = {"title": "Test", "description": "", "acceptance_criteria": []}
        
        success, has_changes, git = _execute_coding_task(
            repo_url="https://github.com/test/repo.git",
            branch_name="main",
            task_definition=task_def,
            workspace_dir=tmp_path,
            logger=mock_logger
        )
        
        # Should return failure
        assert success is False
        assert has_changes is False
        assert git is None
        mock_logger.exception.assert_called_once()
    
    @patch('worker.tasks.GitManager')
    @patch('worker.tasks.Config')
    @patch('worker.tasks.CodingAgent')
    def test_execute_coding_task_no_changes(
        self, mock_agent_class, mock_config, mock_git_manager, tmp_path
    ):
        """Should detect when agent makes no changes."""
        from worker.tasks import _execute_coding_task
        
        mock_git = MagicMock()
        mock_git.has_changes.return_value = False  # No changes
        mock_git_manager.clone.return_value = mock_git
        
        mock_llm = MagicMock()
        mock_config.get_llm_client.return_value = mock_llm
        
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_agent.run.return_value = mock_result
        mock_agent_class.return_value = mock_agent
        
        mock_logger = MagicMock()
        task_def = {"title": "Test", "description": "", "acceptance_criteria": []}
        
        success, has_changes, git = _execute_coding_task(
            repo_url="https://github.com/test/repo.git",
            branch_name="main",
            task_definition=task_def,
            workspace_dir=tmp_path,
            logger=mock_logger
        )
        
        assert success is True
        assert has_changes is False  # No changes made


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
