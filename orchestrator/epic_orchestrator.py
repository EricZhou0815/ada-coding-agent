import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from orchestrator.rule_provider import RuleProvider
from agents.planning_agent import PlanningAgent
from isolation.sandbox import SandboxBackend
from utils.logger import logger


class EpicOrchestrator:
    """
    Higher-level orchestrator that:
    1. Uses PlanningAgent to break a User Story into atomic tasks.
    2. Persists each task as a JSON file in the tasks/<story_id>/ folder.
    3. Runs each task sequentially through an isolated SandboxBackend
       (which internally drives the full CodingAgent → ValidationAgent pipeline).
    """

    def __init__(self, llm_client, tools, tasks_output_dir: str = "tasks", rule_providers: Optional[List[RuleProvider]] = None):
        """
        Args:
            llm_client: LLM client instance used by the PlanningAgent.
            tools: Read-only tools given to the PlanningAgent for codebase exploration.
            tasks_output_dir: Root directory where generated task JSON files are saved.
            rule_providers: Optional list of RuleProviders passed into each Sandbox execution.
        """
        self.planner = PlanningAgent(llm_client, tools)
        self.tasks_output_dir = tasks_output_dir
        self.rule_providers = rule_providers or []

    # ─────────────────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────────────────

    def execute_stories(self, stories: List[Dict], repo_path: str) -> bool:
        """
        Executes an entire backlog of User Stories end-to-end, sequentially.
        
        For each story:
          1. The PlanningAgent plans and persists tasks to disk.
          2. Each task is executed sequentially inside an isolated SandboxBackend.
             The sandbox copies results back to repo_path so subsequent tasks
             see the updated codebase.

        Args:
            stories: List of user story dicts (or a single story dict).
            repo_path: The repository path that will be modified.

        Returns:
            True if all stories and tasks completed successfully.
        """
        if not isinstance(stories, list):
            stories = [stories]

        logger.info("EpicOrchestrator", f"🚀 Analyzing {len(stories)} User Stories from Backlog")
        completed_task_ids = []

        for story in stories:
            story_id = story.get("story_id", "STORY-?")
            logger.info("EpicOrchestrator", f"📚 Story [{story_id}]: {story.get('title', 'Unknown')}")

            # Phase 1: Planning
            task_files = self._plan_and_persist(story, repo_path)
            if not task_files:
                logger.error("EpicOrchestrator", f"Planning failed for Story [{story_id}]. Aborting.")
                return False

            # Phase 2: Sequential Sandbox Execution
            for task_file in task_files:
                task = self._load_task(task_file)
                if not task:
                    logger.error("EpicOrchestrator", f"Could not load task file: {task_file}. Skipping.")
                    continue

                logger.info("EpicOrchestrator", f"\n{'='*60}\n  Task [{task.get('task_id')}]: {task.get('title')}\n{'='*60}")

                success = self._run_task_in_sandbox(task, repo_path, completed_task_ids)
                if not success:
                    logger.error("EpicOrchestrator", f"Task [{task.get('task_id')}] failed. Aborting story [{story_id}].")
                    return False

                completed_task_ids.append(task.get("task_id"))

        logger.success("All User Stories and tasks completed successfully. ✅")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _plan_and_persist(self, story: Dict, repo_path: str) -> List[str]:
        """
        Runs the PlanningAgent on a story, saves each generated task as a JSON
        file under tasks/<story_id>/, and returns the list of file paths.
        """
        logger.step(self.planner.name, "Exploring codebase and generating task list...")
        plan_result = self.planner.run(story, repo_path)

        if not plan_result.success or not plan_result.context_updates.get("generated_tasks"):
            logger.error("EpicOrchestrator", "PlanningAgent did not produce a valid task list.")
            return []

        generated_tasks: List[Dict] = plan_result.context_updates["generated_tasks"]
        story_id = story.get("story_id", "STORY-unknown")

        # Create story-scoped output directory: tasks/<story_id>/
        output_dir = Path(self.tasks_output_dir) / story_id
        output_dir.mkdir(parents=True, exist_ok=True)

        task_files = []
        for task in generated_tasks:
            task_id = task.get("task_id", f"task_{len(task_files)+1}")
            file_path = output_dir / f"{task_id}.json"

            with open(file_path, "w") as f:
                json.dump(task, f, indent=4)

            logger.info("EpicOrchestrator", f"  💾 Saved task [{task_id}] → {file_path}")
            task_files.append(str(file_path))

        logger.success(f"Saved {len(task_files)} tasks for Story [{story_id}] → {output_dir}/")
        return task_files

    def _load_task(self, task_file: str) -> Optional[Dict]:
        """Loads a task dict from a JSON file path."""
        try:
            with open(task_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("EpicOrchestrator", f"Failed to load task file {task_file}: {e}")
            return None

    def _run_task_in_sandbox(self, task: Dict, repo_path: str, completed_task_ids: List[str]) -> bool:
        """
        Spins up a fresh SandboxBackend for a single task and executes it.
        The sandbox isolates the work, then copies the result back to repo_path
        so the next task's sandbox starts from an up-to-date codebase.
        """
        sandbox = SandboxBackend()
        try:
            sandbox.setup(task, repo_path)
            success = sandbox.execute(task, repo_path, completed_task_ids)
            return success
        finally:
            sandbox.cleanup()
