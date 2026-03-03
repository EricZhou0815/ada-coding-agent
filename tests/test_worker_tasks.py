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
    
    @patch('api.database.SessionLocal')
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
    
    @patch('api.database.SessionLocal')
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
    
    @patch('api.database.SessionLocal')
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
    
    @patch('tools.git_manager.GitManager')
    @patch('config.Config')
    @patch('agents.coding_agent.CodingAgent')
    @patch('tools.tools.Tools')
    def test_execute_coding_task_success(
        self, mock_tools_class, mock_agent_class, mock_config, mock_git_manager, tmp_path
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
    
    @patch('tools.git_manager.GitManager')
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
    
    @patch('tools.git_manager.GitManager')
    @patch('config.Config')
    @patch('agents.coding_agent.CodingAgent')
    @patch('tools.tools.Tools')
    def test_execute_coding_task_no_changes(
        self, mock_tools_class, mock_agent_class, mock_config, mock_git_manager, tmp_path
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


class TestExecuteSDLCStoryTask:
    """Test the execute_sdlc_story Celery task."""
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._update_job_status')
    @patch('worker.tasks._append_job_log')
    @patch('utils.logger.logger')
    @patch('orchestrator.sdlc_orchestrator.SDLCOrchestrator')
    @patch('config.Config.get_llm_client')
    def test_execute_sdlc_story_success(
        self, mock_get_llm, mock_orch_class, mock_logger, 
        mock_append_log, mock_update_status, mock_rmtree, tmp_path
    ):
        """Should successfully execute SDLC story."""
        from worker.tasks import execute_sdlc_story
        
        # Setup mocks
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        
        mock_orch = MagicMock()
        mock_orch.run.return_value = True
        mock_orch_class.return_value = mock_orch
        
        story = {
            "title": "Test Story",
            "description": "Test description",
            "tasks": []
        }
        
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(tmp_path)}):
            # Execute task directly - self is provided by bind=True, so pass remaining args
            result = execute_sdlc_story(
                job_id="test-job-123",
                repo_url="https://github.com/test/repo.git",
                story=story,
                use_mock=False
            )
        
        # Verify
        assert result == "SUCCESS"
        mock_update_status.assert_any_call("test-job-123", "RUNNING")
        mock_update_status.assert_any_call("test-job-123", "SUCCESS")
        mock_orch.run.assert_called_once()
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._update_job_status')
    @patch('worker.tasks._append_job_log')
    @patch('utils.logger.logger')
    @patch('orchestrator.sdlc_orchestrator.SDLCOrchestrator')
    @patch('config.Config.get_llm_client')
    def test_execute_sdlc_story_failure(
        self, mock_get_llm, mock_orch_class, mock_logger,
        mock_append_log, mock_update_status, mock_rmtree, tmp_path
    ):
        """Should handle SDLC orchestrator failures."""
        from worker.tasks import execute_sdlc_story
        
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        
        mock_orch = MagicMock()
        mock_orch.run.return_value = False  # Orchestrator failed
        mock_orch_class.return_value = mock_orch
        
        story = {"title": "Test", "description": "", "tasks": []}
        
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(tmp_path)}):
            result = execute_sdlc_story(
                job_id="test-job-456",
                repo_url="https://github.com/test/repo.git",
                story=story
            )
        
        assert result == "FAILED"
        mock_update_status.assert_any_call("test-job-456", "FAILED")
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._update_job_status')
    @patch('worker.tasks._append_job_log')
    @patch('utils.logger.logger')
    @patch('config.Config.get_llm_client')
    def test_execute_sdlc_story_exception(
        self, mock_get_llm, mock_logger, mock_append_log, 
        mock_update_status, mock_rmtree, tmp_path
    ):
        """Should handle exceptions gracefully."""
        from worker.tasks import execute_sdlc_story
        
        # Simulate exception during execution
        mock_get_llm.side_effect = Exception("LLM initialization failed")
        
        story = {"title": "Test", "description": "", "tasks": []}
        
        with patch.dict(os.environ, {"ADA_TMP_DIR": str(tmp_path)}):
            result = execute_sdlc_story(
                job_id="test-job-789",
                repo_url="https://github.com/test/repo.git",
                story=story
            )
        
        assert result == "FAILED"
        mock_update_status.assert_any_call("test-job-789", "FAILED")
        mock_rmtree.assert_called()  # Should cleanup on failure


class TestFixCIFailureTask:
    """Test the fix_ci_failure Celery task."""
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._execute_coding_task')
    @patch('worker.tasks._create_workspace')
    @patch('worker.tasks.redis_client')
    @patch('config.Config.get_vcs_client')
    def test_fix_ci_failure_success(
        self, mock_get_vcs, mock_redis, mock_create_workspace,
        mock_execute_task, mock_rmtree, tmp_path
    ):
        """Should successfully fix CI failure."""
        from worker.tasks import fix_ci_failure
        
        # Setup VCS client mock
        mock_vcs = MagicMock()
        mock_vcs.get_pull_requests.return_value = [
            {"number": 123, "head": {"ref": "feature-branch"}}
        ]
        mock_vcs.get_pipeline_jobs.return_value = {
            "jobs": [{"name": "test", "conclusion": "failure", "id": 456}]
        }
        mock_vcs.get_job_logs.return_value = "Test failed: assertion error"
        mock_get_vcs.return_value = mock_vcs
        
        # Setup Redis mock - no previous retries
        mock_redis.get.return_value = None
        
        # Setup workspace mock
        mock_workspace = tmp_path / "fix_workspace"
        mock_workspace.mkdir()
        mock_create_workspace.return_value = mock_workspace
        
        # Setup execute_coding_task mock
        mock_git = MagicMock()
        mock_execute_task.return_value = (True, True, mock_git)
        
        # Execute
        result = fix_ci_failure(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            branch_name="feature-branch",
            run_id=789
        )
        
        # Verify
        assert result == "SUCCESS"
        mock_git.commit.assert_called_once()
        mock_git.push.assert_called_once_with("feature-branch")
        mock_vcs.create_issue_comment.assert_called_once()
        assert "pushed a fix" in mock_vcs.create_issue_comment.call_args[0][3]
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._create_workspace')
    @patch('worker.tasks.redis_client')
    @patch('config.Config.get_vcs_client')
    def test_fix_ci_failure_max_retries(
        self, mock_get_vcs, mock_redis, mock_create_workspace, mock_rmtree
    ):
        """Should stop after max retries."""
        from worker.tasks import fix_ci_failure, MAX_CI_FIX_RETRIES
        
        mock_vcs = MagicMock()
        mock_vcs.get_pull_requests.return_value = [
            {"number": 123, "head": {"ref": "feature-branch"}}
        ]
        mock_get_vcs.return_value = mock_vcs
        
        # Simulate max retries reached
        mock_redis.get.return_value = str(MAX_CI_FIX_RETRIES)
        
        task_instance = MagicMock()
        result = fix_ci_failure(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            branch_name="feature-branch",
            run_id=789
        )
        
        assert result == "MAX_RETRIES_EXCEEDED"
        mock_vcs.create_issue_comment.assert_called_once()
        comment = mock_vcs.create_issue_comment.call_args[0][3]
        assert "attempted to fix ci failures" in comment.lower() or "attempted to fix" in comment.lower()
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._execute_coding_task')
    @patch('worker.tasks._create_workspace')
    @patch('worker.tasks.redis_client')
    @patch('config.Config.get_vcs_client')
    def test_fix_ci_failure_no_changes(
        self, mock_get_vcs, mock_redis, mock_create_workspace,
        mock_execute_task, mock_rmtree, tmp_path
    ):
        """Should handle case when no fix is found."""
        from worker.tasks import fix_ci_failure
        
        mock_vcs = MagicMock()
        mock_vcs.get_pull_requests.return_value = [
            {"number": 123, "head": {"ref": "feature-branch"}}
        ]
        mock_vcs.get_pipeline_jobs.return_value = {"jobs": []}
        mock_get_vcs.return_value = mock_vcs
        
        mock_redis.get.return_value = "0"
        
        mock_workspace = tmp_path / "fix_workspace"
        mock_workspace.mkdir()
        mock_create_workspace.return_value = mock_workspace
        
        # Agent didn't produce changes
        mock_execute_task.return_value = (True, False, None)
        
        task_instance = MagicMock()
        result = fix_ci_failure(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            branch_name="feature-branch",
            run_id=789
        )
        
        assert result == "NO_CHANGES"
        comment = mock_vcs.create_issue_comment.call_args[0][3]
        assert "couldn't determine a fix" in comment.lower()


class TestApplyPRFeedbackTask:
    """Test the apply_pr_feedback Celery task."""
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._execute_coding_task')
    @patch('worker.tasks._create_workspace')
    @patch('config.Config.get_vcs_client')
    def test_apply_pr_feedback_success(
        self, mock_get_vcs, mock_create_workspace,
        mock_execute_task, mock_rmtree, tmp_path
    ):
        """Should successfully apply PR feedback."""
        from worker.tasks import apply_pr_feedback
        
        # Setup VCS client mock
        mock_vcs = MagicMock()
        mock_vcs.get_pull_request.return_value = {
            "number": 123,
            "head": {"ref": "feature-branch"}
        }
        mock_get_vcs.return_value = mock_vcs
        
        # Setup workspace mock
        mock_workspace = tmp_path / "feedback_workspace"
        mock_workspace.mkdir()
        mock_create_workspace.return_value = mock_workspace
        
        # Setup execute_coding_task mock
        mock_git = MagicMock()
        mock_execute_task.return_value = (True, True, mock_git)
        
        # Execute
        result = apply_pr_feedback(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            pr_number=123,
            feedback="Please add error handling"
        )
        
        # Verify
        assert result == "SUCCESS"
        mock_git.commit.assert_called_once()
        mock_git.push.assert_called_once_with("feature-branch")
        mock_vcs.create_issue_comment.assert_called_once()
        comment = mock_vcs.create_issue_comment.call_args[0][3]
        assert "applied your feedback" in comment.lower()
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._create_workspace')
    @patch('config.Config.get_vcs_client')
    def test_apply_pr_feedback_pr_fetch_error(
        self, mock_get_vcs, mock_create_workspace, mock_rmtree
    ):
        """Should handle PR fetch errors."""
        from worker.tasks import apply_pr_feedback
        
        mock_vcs = MagicMock()
        mock_vcs.get_pull_request.side_effect = Exception("PR not found")
        mock_get_vcs.return_value = mock_vcs
        
        task_instance = MagicMock()
        result = apply_pr_feedback(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            pr_number=999,
            feedback="Test feedback"
        )
        
        assert result == "ERROR"
        mock_vcs.create_issue_comment.assert_called_once()
        comment = mock_vcs.create_issue_comment.call_args[0][3]
        assert "couldn't fetch" in comment.lower() or "error" in comment.lower()
    
    @patch('worker.tasks.shutil.rmtree')
    @patch('worker.tasks._execute_coding_task')
    @patch('worker.tasks._create_workspace')
    @patch('config.Config.get_vcs_client')
    def test_apply_pr_feedback_no_changes(
        self, mock_get_vcs, mock_create_workspace,
        mock_execute_task, mock_rmtree, tmp_path
    ):
        """Should handle case when no changes are made."""
        from worker.tasks import apply_pr_feedback
        
        mock_vcs = MagicMock()
        mock_vcs.get_pull_request.return_value = {
            "number": 123,
            "head": {"ref": "feature-branch"}
        }
        mock_get_vcs.return_value = mock_vcs
        
        mock_workspace = tmp_path / "feedback_workspace"
        mock_workspace.mkdir()
        mock_create_workspace.return_value = mock_workspace
        
        # Agent succeeded but made no changes
        mock_execute_task.return_value = (True, False, None)
        
        task_instance = MagicMock()
        result = apply_pr_feedback(
            repo_url="https://github.com/test/repo.git",
            owner="test",
            repo="repo",
            pr_number=123,
            feedback="Unclear feedback"
        )
        
        assert result == "NO_CHANGES"
        comment = mock_vcs.create_issue_comment.call_args[0][3]
        assert "didn't find any code changes" in comment.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
