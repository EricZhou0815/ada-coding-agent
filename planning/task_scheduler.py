"""
planning/task_scheduler.py

Selects and dispatches tasks whose dependencies are satisfied.
Drives the execution loop over the TaskGraph.
"""

from typing import Callable, Optional
from utils.logger import logger
from planning.models import Task, TaskStatus, RunExecution, RunStatus
from planning.task_graph import TaskGraph


class TaskScheduler:
    """
    Iterates the TaskGraph, dispatching ready tasks to an executor callback.
    Supports retries per task and aborts on unrecoverable failures.
    """

    def __init__(self, graph: TaskGraph, max_retries: int = 3):
        """
        Args:
            graph: A validated TaskGraph (DAG).
            max_retries: Maximum retries per task before marking it failed.
        """
        self.graph = graph
        self.max_retries = max_retries
        self.runs: list[RunExecution] = []

    def run(self, executor: Callable[[Task, RunExecution], bool]) -> bool:
        """
        Execute all tasks in dependency order.

        Args:
            executor: A callable(task, run) -> bool that executes a single task.
                      Returns True on success, False on failure.

        Returns:
            True if all tasks completed successfully, False otherwise.
        """
        while not self.graph.all_completed():
            ready = self.graph.get_ready_tasks()

            if not ready:
                if self.graph.has_failed():
                    logger.error("TaskScheduler", "No ready tasks and some tasks failed — aborting.")
                    return False
                # Shouldn't happen in a valid DAG without failures
                logger.error("TaskScheduler", "Deadlock detected — no tasks are ready.")
                return False

            for task in ready:
                success = self._execute_with_retries(task, executor)
                if not success:
                    logger.error("TaskScheduler", f"Task '{task.task_id}' failed after {self.max_retries} retries.")
                    self.graph.mark_failed(task.task_id)
                    return False

        logger.success("All tasks completed successfully.")
        return True

    def _execute_with_retries(self, task: Task, executor: Callable[[Task, RunExecution], bool]) -> bool:
        """Execute a single task with retry support."""
        run = RunExecution(
            task_id=task.task_id,
            max_retries=self.max_retries,
        )
        self.runs.append(run)

        while run.can_retry:
            self.graph.mark_running(task.task_id)
            run.status = RunStatus.RUNNING
            run.log(f"Attempt {run.retry_count + 1}/{run.max_retries}")

            logger.info("TaskScheduler", f"▶ Executing task '{task.title}' (attempt {run.retry_count + 1})")

            success = executor(task, run)

            if success:
                self.graph.mark_completed(task.task_id)
                run.status = RunStatus.SUCCESS
                run.log("Task completed successfully")
                logger.success(f"Task '{task.title}' completed.")
                return True

            run.retry_count += 1
            if run.can_retry:
                run.status = RunStatus.RETRYING
                run.log(f"Retrying ({run.retry_count}/{run.max_retries})")
                logger.warning("TaskScheduler", f"↻ Retrying task '{task.title}' ({run.retry_count}/{run.max_retries})")

        run.status = RunStatus.FAILED
        run.log("All retries exhausted")
        return False
