"""Tests for planning/task_scheduler.py — task scheduling with retries."""

import pytest
from unittest.mock import Mock
from planning.models import Task, TaskType, TaskStatus, RunExecution, RunStatus
from planning.task_graph import TaskGraph
from planning.task_scheduler import TaskScheduler


def _make_task(task_id, deps=None):
    return Task(
        task_id=task_id,
        plan_id="plan_test",
        title=f"Task {task_id}",
        description=f"Desc for {task_id}",
        type=TaskType.BACKEND,
        dependencies=deps or [],
    )


class TestTaskSchedulerSuccess:
    def test_single_task_success(self):
        graph = TaskGraph([_make_task("t1")])
        scheduler = TaskScheduler(graph, max_retries=3)

        executor = Mock(return_value=True)
        result = scheduler.run(executor)

        assert result is True
        assert graph.all_completed()
        executor.assert_called_once()

    def test_chain_executes_in_order(self):
        tasks = [
            _make_task("t1"),
            _make_task("t2", deps=["t1"]),
            _make_task("t3", deps=["t2"]),
        ]
        graph = TaskGraph(tasks)
        scheduler = TaskScheduler(graph, max_retries=3)

        execution_order = []

        def executor(task, run):
            execution_order.append(task.task_id)
            return True

        result = scheduler.run(executor)

        assert result is True
        assert execution_order == ["t1", "t2", "t3"]

    def test_independent_tasks_all_execute(self):
        tasks = [_make_task("a"), _make_task("b"), _make_task("c")]
        graph = TaskGraph(tasks)
        scheduler = TaskScheduler(graph, max_retries=3)

        executed = []

        def executor(task, run):
            executed.append(task.task_id)
            return True

        result = scheduler.run(executor)

        assert result is True
        assert sorted(executed) == ["a", "b", "c"]


class TestTaskSchedulerRetries:
    def test_retry_then_succeed(self):
        graph = TaskGraph([_make_task("t1")])
        scheduler = TaskScheduler(graph, max_retries=3)

        call_count = 0

        def executor(task, run):
            nonlocal call_count
            call_count += 1
            return call_count >= 2  # Fails first, succeeds second

        result = scheduler.run(executor)

        assert result is True
        assert call_count == 2

    def test_max_retries_exhausted(self):
        graph = TaskGraph([_make_task("t1")])
        scheduler = TaskScheduler(graph, max_retries=2)

        executor = Mock(return_value=False)
        result = scheduler.run(executor)

        assert result is False
        assert executor.call_count == 2

    def test_retry_count_tracked_in_run(self):
        graph = TaskGraph([_make_task("t1")])
        scheduler = TaskScheduler(graph, max_retries=3)

        executor = Mock(return_value=False)
        scheduler.run(executor)

        assert len(scheduler.runs) == 1
        run = scheduler.runs[0]
        assert run.retry_count == 3
        assert run.status == RunStatus.FAILED


class TestTaskSchedulerFailure:
    def test_failure_aborts_remaining(self):
        tasks = [
            _make_task("t1"),
            _make_task("t2", deps=["t1"]),
        ]
        graph = TaskGraph(tasks)
        scheduler = TaskScheduler(graph, max_retries=1)

        executor = Mock(return_value=False)
        result = scheduler.run(executor)

        assert result is False
        # Only t1 should have been attempted (it failed, so t2 never runs)
        assert executor.call_count == 1

    def test_failed_task_blocks_dependents(self):
        tasks = [
            _make_task("t1"),
            _make_task("t2", deps=["t1"]),
        ]
        graph = TaskGraph(tasks)
        scheduler = TaskScheduler(graph, max_retries=1)

        executor = Mock(return_value=False)
        scheduler.run(executor)

        t1 = graph.get_task("t1")
        t2 = graph.get_task("t2")
        assert t1.status == TaskStatus.FAILED
        assert t2.status == TaskStatus.PENDING  # Never reached


class TestTaskSchedulerRuns:
    def test_runs_tracked(self):
        tasks = [_make_task("t1"), _make_task("t2")]
        graph = TaskGraph(tasks)
        scheduler = TaskScheduler(graph, max_retries=3)

        executor = Mock(return_value=True)
        scheduler.run(executor)

        assert len(scheduler.runs) == 2
        for run in scheduler.runs:
            assert run.status == RunStatus.SUCCESS

    def test_run_logs_populated(self):
        graph = TaskGraph([_make_task("t1")])
        scheduler = TaskScheduler(graph, max_retries=3)

        executor = Mock(return_value=True)
        scheduler.run(executor)

        run = scheduler.runs[0]
        assert len(run.logs) > 0
        assert "Attempt 1/3" in run.logs[0]
