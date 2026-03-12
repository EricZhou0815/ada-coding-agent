"""
planning/task_graph.py

Builds and manages a Directed Acyclic Graph (DAG) of tasks.
Provides topological ordering, cycle detection, and dependency resolution.
"""

from typing import List, Dict, Set, Optional
from collections import defaultdict, deque

from planning.models import Task, TaskStatus


class CycleError(Exception):
    """Raised when a cycle is detected in the task graph."""
    pass


class TaskGraph:
    """
    Represents task dependency relationships as a DAG.
    Provides resolution of execution order and readiness checks.
    """

    def __init__(self, tasks: List[Task]):
        """
        Build a task graph from a list of tasks.

        Args:
            tasks: List of Task objects with dependency references.

        Raises:
            CycleError: If the dependency graph contains a cycle.
            ValueError: If a task references a non-existent dependency.
        """
        self._tasks: Dict[str, Task] = {t.task_id: t for t in tasks}
        self._adjacency: Dict[str, List[str]] = defaultdict(list)  # dependency -> dependents
        self._reverse: Dict[str, List[str]] = defaultdict(list)    # dependent -> dependencies

        self._build(tasks)
        self._validate_acyclic()

    def _build(self, tasks: List[Task]) -> None:
        """Build adjacency lists from task dependencies."""
        task_ids = set(self._tasks.keys())
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(
                        f"Task '{task.task_id}' depends on '{dep_id}' which does not exist"
                    )
                self._adjacency[dep_id].append(task.task_id)
                self._reverse[task.task_id].append(dep_id)

    def _validate_acyclic(self) -> None:
        """Verify the graph is a DAG using Kahn's algorithm."""
        in_degree = {tid: 0 for tid in self._tasks}
        for tid in self._tasks:
            for dep in self._reverse.get(tid, []):
                in_degree[tid] += 1

        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for dependent in self._adjacency.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if visited_count != len(self._tasks):
            raise CycleError("Task dependency graph contains a cycle")

    def get_ready_tasks(self) -> List[Task]:
        """
        Return tasks whose dependencies are all completed.
        These tasks are eligible for execution.
        """
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            deps = self._reverse.get(task.task_id, [])
            if all(self._tasks[d].status == TaskStatus.COMPLETED for d in deps):
                ready.append(task)
        return ready

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def mark_completed(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED

    def mark_failed(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED

    def mark_running(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.RUNNING

    def all_completed(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self._tasks.values())

    def has_failed(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self._tasks.values())

    def topological_order(self) -> List[Task]:
        """Return tasks in a valid topological execution order."""
        in_degree = {tid: len(self._reverse.get(tid, [])) for tid in self._tasks}
        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        order = []

        while queue:
            node = queue.popleft()
            order.append(self._tasks[node])
            for dependent in self._adjacency.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        return order

    @property
    def tasks(self) -> List[Task]:
        return list(self._tasks.values())

    def __len__(self) -> int:
        return len(self._tasks)
