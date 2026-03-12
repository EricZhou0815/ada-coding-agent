"""Tests for verification/quality_gate.py — deterministic verification pipeline."""

import pytest
import os
from unittest.mock import patch, Mock
from planning.models import Task, TaskType
from verification.quality_gate import QualityGate


def _make_task(task_id="t1"):
    return Task(
        task_id=task_id,
        plan_id="plan_test",
        title="Test task",
        description="Description",
        type=TaskType.BACKEND,
        success_criteria=["tests pass"],
    )


class TestQualityGateDetection:
    def test_detects_python_project(self, tmp_path):
        (tmp_path / "pytest.ini").write_text("[pytest]")
        gate = QualityGate(str(tmp_path))
        assert gate._profile is not None
        assert gate._profile["marker"] == "pytest.ini"

    def test_detects_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        gate = QualityGate(str(tmp_path))
        assert gate._profile is not None
        assert gate._profile["marker"] == "package.json"

    def test_no_profile_detected(self, tmp_path):
        gate = QualityGate(str(tmp_path))
        assert gate._profile is None


class TestQualityGateVerify:
    def test_no_profile_passes_all(self, tmp_path):
        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.validation_passed is True
        assert result.tests_passed is True
        assert result.lint_passed is True
        assert result.build_passed is True

    @patch("subprocess.run")
    def test_all_checks_pass(self, mock_run, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.validation_passed is True
        assert mock_run.call_count == 3  # lint, build, test

    @patch("subprocess.run")
    def test_test_failure(self, mock_run, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        # lint passes, build passes, test fails
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),   # lint
            Mock(returncode=0, stdout="", stderr=""),   # build
            Mock(returncode=1, stdout="FAILED", stderr=""),  # test
        ]

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.validation_passed is False
        assert result.tests_passed is False
        assert result.lint_passed is True
        assert result.build_passed is True

    @patch("subprocess.run")
    def test_lint_failure(self, mock_run, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        mock_run.side_effect = [
            Mock(returncode=1, stdout="errors", stderr=""),  # lint fails
            Mock(returncode=0, stdout="", stderr=""),         # build
            Mock(returncode=0, stdout="", stderr=""),         # test
        ]

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.validation_passed is False
        assert result.lint_passed is False

    @patch("subprocess.run")
    def test_python_project_skips_lint_and_build(self, mock_run, tmp_path):
        (tmp_path / "pytest.ini").write_text("[pytest]")
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.validation_passed is True
        # Only test command should be called (lint and build are None for pytest profile)
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_timeout_treated_as_failure(self, mock_run, tmp_path):
        import subprocess
        (tmp_path / "pytest.ini").write_text("[pytest]")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=300)

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        assert result.tests_passed is False
        assert result.validation_passed is False

    @patch("subprocess.run")
    def test_command_not_found_passes(self, mock_run, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        mock_run.side_effect = FileNotFoundError("npm not found")

        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task())

        # FileNotFoundError means tool not installed, pass gracefully
        assert result.validation_passed is True

    def test_task_id_in_result(self, tmp_path):
        gate = QualityGate(str(tmp_path))
        result = gate.verify(_make_task("my_task"))
        assert result.task_id == "my_task"
