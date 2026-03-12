"""Tests for planning/models.py — Phase 3 data models."""

import pytest
from planning.models import (
    Task, TaskType, TaskStatus,
    ImplementationPlan,
    VerificationResult,
    RunExecution, RunStatus,
    FeatureStatus,
)


# ── Task ───────────────────────────────────────────────────────────────────

class TestTask:
    def test_create_task(self):
        t = Task(
            task_id="task_1",
            plan_id="plan_abc",
            title="Add users table",
            description="Create migration",
            type=TaskType.DATABASE,
        )
        assert t.task_id == "task_1"
        assert t.status == TaskStatus.PENDING
        assert t.dependencies == []
        assert t.success_criteria == []

    def test_task_to_dict(self):
        t = Task(
            task_id="task_1",
            plan_id="plan_abc",
            title="Add endpoint",
            description="REST endpoint",
            type=TaskType.API,
            dependencies=["task_0"],
            success_criteria=["returns 200"],
        )
        d = t.to_dict()
        assert d["task_id"] == "task_1"
        assert d["type"] == "api"
        assert d["dependencies"] == ["task_0"]
        assert d["status"] == "pending"

    def test_task_from_dict(self):
        data = {
            "task_id": "task_2",
            "plan_id": "p1",
            "title": "Write tests",
            "description": "Unit tests",
            "type": "test",
            "dependencies": ["task_1"],
            "status": "completed",
            "success_criteria": ["all green"],
        }
        t = Task.from_dict(data)
        assert t.task_id == "task_2"
        assert t.type == TaskType.TEST
        assert t.status == TaskStatus.COMPLETED
        assert t.dependencies == ["task_1"]

    def test_task_from_dict_defaults(self):
        data = {
            "task_id": "task_x",
            "plan_id": "p1",
            "title": "Refactor",
            "description": "Clean up",
            "type": "refactor",
        }
        t = Task.from_dict(data)
        assert t.status == TaskStatus.PENDING
        assert t.dependencies == []
        assert t.success_criteria == []

    def test_task_types(self):
        for val in ["database", "backend", "frontend", "api", "test", "refactor", "config"]:
            assert TaskType(val).value == val


# ── ImplementationPlan ─────────────────────────────────────────────────────

class TestImplementationPlan:
    def test_create_plan(self):
        plan = ImplementationPlan(
            plan_id="plan_1",
            feature_title="Password Reset",
            feature_description="Allow resetting passwords",
            tasks=[
                Task("t1", "plan_1", "Schema", "Migration", TaskType.DATABASE),
                Task("t2", "plan_1", "Endpoint", "API route", TaskType.API, dependencies=["t1"]),
            ],
            success_criteria=["users can reset password"],
        )
        assert len(plan.tasks) == 2
        assert plan.feature_title == "Password Reset"

    def test_plan_to_dict(self):
        plan = ImplementationPlan(
            plan_id="p1",
            feature_title="Feature",
            feature_description="Desc",
            tasks=[Task("t1", "p1", "T", "D", TaskType.BACKEND)],
        )
        d = plan.to_dict()
        assert d["plan_id"] == "p1"
        assert len(d["tasks"]) == 1
        assert d["tasks"][0]["task_id"] == "t1"

    def test_plan_from_dict(self):
        data = {
            "plan_id": "p2",
            "feature_title": "Auth Feature",
            "feature_description": "OAuth integration",
            "tasks": [
                {"task_id": "t1", "title": "Setup", "description": "Config", "type": "config"},
                {"task_id": "t2", "title": "Logic", "description": "Backend", "type": "backend", "dependencies": ["t1"]},
            ],
            "success_criteria": ["login works"],
        }
        plan = ImplementationPlan.from_dict(data)
        assert plan.plan_id == "p2"
        assert len(plan.tasks) == 2
        assert plan.tasks[1].dependencies == ["t1"]
        # from_dict injects plan_id into tasks
        assert plan.tasks[0].plan_id == "p2"

    def test_plan_get_task(self):
        plan = ImplementationPlan(
            plan_id="p1",
            feature_title="F",
            feature_description="D",
            tasks=[
                Task("t1", "p1", "A", "B", TaskType.BACKEND),
                Task("t2", "p1", "C", "D", TaskType.TEST),
            ],
        )
        assert plan.get_task("t1").title == "A"
        assert plan.get_task("t2").title == "C"
        assert plan.get_task("t99") is None

    def test_plan_from_dict_auto_plan_id(self):
        data = {
            "feature_title": "Auto ID",
            "feature_description": "No explicit plan_id",
            "tasks": [],
        }
        plan = ImplementationPlan.from_dict(data)
        assert plan.plan_id  # auto-generated UUID


# ── VerificationResult ─────────────────────────────────────────────────────

class TestVerificationResult:
    def test_all_pass(self):
        v = VerificationResult(task_id="t1", tests_passed=True, lint_passed=True, build_passed=True)
        assert v.validation_passed is True

    def test_partial_fail(self):
        v = VerificationResult(task_id="t1", tests_passed=True, lint_passed=False, build_passed=True)
        assert v.validation_passed is False

    def test_to_dict(self):
        v = VerificationResult(task_id="t1", tests_passed=True, lint_passed=True, build_passed=True, details="ok")
        d = v.to_dict()
        assert d["validation_passed"] is True
        assert d["details"] == "ok"


# ── RunExecution ───────────────────────────────────────────────────────────

class TestRunExecution:
    def test_defaults(self):
        r = RunExecution(task_id="t1")
        assert r.status == RunStatus.PENDING
        assert r.retry_count == 0
        assert r.max_retries == 3
        assert r.can_retry is True
        assert r.run_id  # auto-generated

    def test_can_retry_exhausted(self):
        r = RunExecution(task_id="t1", retry_count=3, max_retries=3)
        assert r.can_retry is False

    def test_log(self):
        r = RunExecution(task_id="t1")
        r.log("hello")
        r.log("world")
        assert r.logs == ["hello", "world"]

    def test_to_dict(self):
        r = RunExecution(task_id="t1", status=RunStatus.RUNNING)
        d = r.to_dict()
        assert d["task_id"] == "t1"
        assert d["status"] == "running"
        assert d["result"] is None

    def test_to_dict_with_result(self):
        v = VerificationResult(task_id="t1", tests_passed=True, lint_passed=True, build_passed=True)
        r = RunExecution(task_id="t1", result=v)
        d = r.to_dict()
        assert d["result"]["validation_passed"] is True


# ── Enums ──────────────────────────────────────────────────────────────────

class TestEnums:
    def test_feature_status_values(self):
        assert FeatureStatus.PENDING.value == "pending"
        assert FeatureStatus.IN_PROGRESS.value == "in_progress"
        assert FeatureStatus.COMPLETED.value == "completed"
        assert FeatureStatus.FAILED.value == "failed"

    def test_run_status_values(self):
        assert RunStatus.RETRYING.value == "retrying"
        assert RunStatus.SUCCESS.value == "success"
