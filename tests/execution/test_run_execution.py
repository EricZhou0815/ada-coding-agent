"""Tests for execution/run_execution.py — task execution engine."""

import pytest
import os
import shutil
from unittest.mock import patch, Mock, MagicMock
from planning.models import Task, TaskType, RunExecution, VerificationResult
from execution.run_execution import ExecutionEngine


def _make_task(task_id="t1"):
    return Task(
        task_id=task_id,
        plan_id="plan_test",
        title="Implement feature",
        description="Add the feature",
        type=TaskType.BACKEND,
        success_criteria=["tests pass"],
    )


class TestExecutionEngineTaskToStory:
    def test_converts_task_to_story_format(self):
        engine = ExecutionEngine(llm_client=Mock(), workspace_root="/tmp/ws")
        task = _make_task()
        story = engine._task_to_story(task)

        assert story["story_id"] == "t1"
        assert story["title"] == "Implement feature"
        assert story["description"] == "Add the feature"
        assert story["acceptance_criteria"] == ["tests pass"]


class TestExecutionEngineWorkspace:
    def test_setup_workspace_creates_copy(self, tmp_path):
        # Create a mock repo
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("print('hello')")
        (repo / "subdir").mkdir()
        (repo / "subdir" / "file.txt").write_text("data")

        engine = ExecutionEngine(llm_client=Mock(), workspace_root=str(tmp_path / "workspaces"))
        isolated = str(tmp_path / "workspaces" / "isolated_repo")
        engine._setup_workspace(str(repo), isolated)

        assert os.path.exists(os.path.join(isolated, "main.py"))
        assert os.path.exists(os.path.join(isolated, "subdir", "file.txt"))

    def test_setup_workspace_replaces_existing(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "file.py").write_text("v2")

        isolated = tmp_path / "workspaces" / "isolated"
        isolated.mkdir(parents=True)
        (isolated / "old_file.py").write_text("old")

        engine = ExecutionEngine(llm_client=Mock(), workspace_root=str(tmp_path / "workspaces"))
        engine._setup_workspace(str(repo), str(isolated))

        assert os.path.exists(str(isolated / "file.py"))
        assert not os.path.exists(str(isolated / "old_file.py"))


class TestExecutionEngineCopyBack:
    def test_copy_results_back(self, tmp_path):
        # Create isolated repo with modified files
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        (isolated / "new_file.py").write_text("new content")
        (isolated / "modified.py").write_text("modified")

        # Create original repo
        original = tmp_path / "original"
        original.mkdir()
        (original / "modified.py").write_text("original")

        engine = ExecutionEngine(llm_client=Mock(), workspace_root=str(tmp_path))
        engine._copy_results_back(str(isolated), str(original))

        assert (original / "new_file.py").read_text() == "new content"
        assert (original / "modified.py").read_text() == "modified"


class TestExecutionEngineCleanup:
    def test_cleanup_workspace(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "file.txt").write_text("data")

        engine = ExecutionEngine(llm_client=Mock(), workspace_root=str(tmp_path))
        engine._cleanup_workspace(str(workspace))

        assert not os.path.exists(str(workspace))

    def test_cleanup_nonexistent_is_safe(self, tmp_path):
        engine = ExecutionEngine(llm_client=Mock(), workspace_root=str(tmp_path))
        # Should not raise
        engine._cleanup_workspace(str(tmp_path / "nonexistent"))
