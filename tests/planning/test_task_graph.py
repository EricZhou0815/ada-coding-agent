"""Tests for planning/task_graph.py — DAG validation and dependency resolution."""

import pytest
from planning.models import Task, TaskType, TaskStatus
from planning.task_graph import TaskGraph, CycleError


def _make_task(task_id, deps=None):
    """Helper to create a simple task."""
    return Task(
        task_id=task_id,
        plan_id="plan_test",
        title=f"Task {task_id}",
        description=f"Desc for {task_id}",
        type=TaskType.BACKEND,
        dependencies=deps or [],
    )


# ── Construction & Validation ──────────────────────────────────────────────

class TestTaskGraphConstruction:
    def test_simple_chain(self):
        """task_1 -> task_2 -> task_3"""
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
            _make_task("task_3", deps=["task_2"]),
        ]
        graph = TaskGraph(tasks)
        assert len(graph) == 3

    def test_diamond_shape(self):
        """task_1 -> task_2, task_1 -> task_3, task_2+task_3 -> task_4"""
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
            _make_task("task_3", deps=["task_1"]),
            _make_task("task_4", deps=["task_2", "task_3"]),
        ]
        graph = TaskGraph(tasks)
        assert len(graph) == 4

    def test_independent_tasks(self):
        tasks = [_make_task("a"), _make_task("b"), _make_task("c")]
        graph = TaskGraph(tasks)
        assert len(graph) == 3

    def test_single_task(self):
        graph = TaskGraph([_make_task("only")])
        assert len(graph) == 1

    def test_cycle_detection(self):
        """task_1 -> task_2 -> task_1 is a cycle."""
        tasks = [
            _make_task("task_1", deps=["task_2"]),
            _make_task("task_2", deps=["task_1"]),
        ]
        with pytest.raises(CycleError):
            TaskGraph(tasks)

    def test_self_cycle_detection(self):
        tasks = [_make_task("task_1", deps=["task_1"])]
        with pytest.raises(CycleError):
            TaskGraph(tasks)

    def test_three_node_cycle(self):
        tasks = [
            _make_task("a", deps=["c"]),
            _make_task("b", deps=["a"]),
            _make_task("c", deps=["b"]),
        ]
        with pytest.raises(CycleError):
            TaskGraph(tasks)

    def test_missing_dependency_raises(self):
        tasks = [_make_task("task_1", deps=["nonexistent"])]
        with pytest.raises(ValueError, match="nonexistent"):
            TaskGraph(tasks)


# ── Readiness ──────────────────────────────────────────────────────────────

class TestGetReadyTasks:
    def test_root_tasks_are_ready(self):
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
        ]
        graph = TaskGraph(tasks)
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "task_1"

    def test_all_independent_ready(self):
        tasks = [_make_task("a"), _make_task("b"), _make_task("c")]
        graph = TaskGraph(tasks)
        ready = graph.get_ready_tasks()
        assert len(ready) == 3

    def test_dependent_unblocked_after_completion(self):
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
        ]
        graph = TaskGraph(tasks)
        graph.mark_completed("task_1")

        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "task_2"

    def test_diamond_unblocking(self):
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
            _make_task("task_3", deps=["task_1"]),
            _make_task("task_4", deps=["task_2", "task_3"]),
        ]
        graph = TaskGraph(tasks)

        # Only task_1 ready initially
        assert [t.task_id for t in graph.get_ready_tasks()] == ["task_1"]

        graph.mark_completed("task_1")
        ready_ids = sorted(t.task_id for t in graph.get_ready_tasks())
        assert ready_ids == ["task_2", "task_3"]

        graph.mark_completed("task_2")
        # task_4 still blocked — task_3 not done
        assert [t.task_id for t in graph.get_ready_tasks()] == ["task_3"]

        graph.mark_completed("task_3")
        assert [t.task_id for t in graph.get_ready_tasks()] == ["task_4"]

    def test_running_tasks_not_ready(self):
        tasks = [_make_task("task_1")]
        graph = TaskGraph(tasks)
        graph.mark_running("task_1")
        assert graph.get_ready_tasks() == []


# ── Status ─────────────────────────────────────────────────────────────────

class TestGraphStatus:
    def test_all_completed(self):
        tasks = [_make_task("a"), _make_task("b")]
        graph = TaskGraph(tasks)
        assert graph.all_completed() is False
        graph.mark_completed("a")
        assert graph.all_completed() is False
        graph.mark_completed("b")
        assert graph.all_completed() is True

    def test_has_failed(self):
        tasks = [_make_task("a"), _make_task("b")]
        graph = TaskGraph(tasks)
        assert graph.has_failed() is False
        graph.mark_failed("a")
        assert graph.has_failed() is True


# ── Topological Order ──────────────────────────────────────────────────────

class TestTopologicalOrder:
    def test_chain_order(self):
        tasks = [
            _make_task("task_3", deps=["task_2"]),
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
        ]
        graph = TaskGraph(tasks)
        order = [t.task_id for t in graph.topological_order()]
        assert order.index("task_1") < order.index("task_2")
        assert order.index("task_2") < order.index("task_3")

    def test_diamond_order(self):
        tasks = [
            _make_task("task_1"),
            _make_task("task_2", deps=["task_1"]),
            _make_task("task_3", deps=["task_1"]),
            _make_task("task_4", deps=["task_2", "task_3"]),
        ]
        graph = TaskGraph(tasks)
        order = [t.task_id for t in graph.topological_order()]
        assert order[0] == "task_1"
        assert order[-1] == "task_4"

    def test_independent_all_present(self):
        tasks = [_make_task("x"), _make_task("y"), _make_task("z")]
        graph = TaskGraph(tasks)
        order = [t.task_id for t in graph.topological_order()]
        assert sorted(order) == ["x", "y", "z"]
