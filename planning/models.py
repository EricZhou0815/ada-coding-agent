"""
planning/models.py

Core data models for the Phase 3 deterministic planning and execution architecture.

All agents operate on structured models rather than raw prompts.
"""

import uuid
from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


class TaskType(str, Enum):
    DATABASE = "database"
    BACKEND = "backend"
    FRONTEND = "frontend"
    API = "api"
    TEST = "test"
    REFACTOR = "refactor"
    CONFIG = "config"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class FeatureStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Atomic unit of engineering work. Each task maps to one coding agent execution."""
    task_id: str
    plan_id: str
    title: str
    description: str
    type: TaskType
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    success_criteria: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "title": self.title,
            "description": self.description,
            "type": self.type.value,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "success_criteria": self.success_criteria,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Task":
        return Task(
            task_id=data["task_id"],
            plan_id=data["plan_id"],
            title=data["title"],
            description=data["description"],
            type=TaskType(data.get("type", "backend")),
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            success_criteria=data.get("success_criteria", []),
        )


@dataclass
class ImplementationPlan:
    """Represents the high-level plan for implementing a feature."""
    plan_id: str
    feature_title: str
    feature_description: str
    tasks: List[Task] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "feature_title": self.feature_title,
            "feature_description": self.feature_description,
            "tasks": [t.to_dict() for t in self.tasks],
            "success_criteria": self.success_criteria,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ImplementationPlan":
        plan_id = data.get("plan_id", str(uuid.uuid4()))
        tasks = [Task.from_dict({**t, "plan_id": plan_id}) for t in data.get("tasks", [])]
        return ImplementationPlan(
            plan_id=plan_id,
            feature_title=data["feature_title"],
            feature_description=data.get("feature_description", ""),
            tasks=tasks,
            success_criteria=data.get("success_criteria", []),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )

    def get_task(self, task_id: str) -> Optional[Task]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None


@dataclass
class VerificationResult:
    """Represents task validation outcome from the quality gate."""
    task_id: str
    tests_passed: bool = False
    lint_passed: bool = False
    build_passed: bool = False
    details: str = ""

    @property
    def validation_passed(self) -> bool:
        return self.tests_passed and self.lint_passed and self.build_passed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tests_passed": self.tests_passed,
            "lint_passed": self.lint_passed,
            "build_passed": self.build_passed,
            "validation_passed": self.validation_passed,
            "details": self.details,
        }


@dataclass
class RunExecution:
    """Represents a single coding agent execution for a task."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    status: RunStatus = RunStatus.PENDING
    workspace_path: str = ""
    branch: str = ""
    retry_count: int = 0
    max_retries: int = 3
    logs: List[str] = field(default_factory=list)
    result: Optional[VerificationResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "workspace_path": self.workspace_path,
            "branch": self.branch,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "logs": self.logs,
            "result": self.result.to_dict() if self.result else None,
        }

    def log(self, message: str) -> None:
        self.logs.append(message)

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
