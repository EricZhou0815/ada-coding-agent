"""
orchestration/plan_orchestrator.py

Top-level orchestrator for Phase 3 deterministic planning and execution.

Workflow:
  1. PlannerAgent converts a user story into an ImplementationPlan
  2. TaskGraph validates the DAG
  3. TaskScheduler dispatches ready tasks
  4. ExecutionEngine runs each task through the CodingAgent pipeline
  5. QualityGate verifies each task deterministically
"""

import os
from typing import Dict, List, Optional

from planning.models import ImplementationPlan, Task, RunExecution, FeatureStatus
from planning.planner_agent import PlannerAgent
from planning.task_graph import TaskGraph, CycleError
from planning.task_scheduler import TaskScheduler
from execution.run_execution import ExecutionEngine
from intelligence.repo_graph_builder import RepoGraphBuilder, RepoGraph
from intelligence.context_retriever import ContextRetriever
from utils.logger import logger


class PlanOrchestrator:
    """
    Orchestrates the full Plan → TaskGraph → Execute → Verify pipeline.
    
    This replaces the simple sequential execution in EpicOrchestrator
    with DAG-based deterministic planning and task scheduling.
    """

    def __init__(
        self,
        llm_client,
        tools,
        workspace_root: str,
        rule_providers=None,
        max_task_retries: int = 3,
        max_pipeline_retries: int = 25,
    ):
        """
        Args:
            llm_client: LLM client for planning and coding.
            tools: Tools instance for repo exploration.
            workspace_root: Root directory for task workspaces.
            rule_providers: Quality gate rule providers.
            max_task_retries: Max retries per task in the scheduler.
            max_pipeline_retries: Max retries for the CodingAgent→Validation inner loop.
        """
        self.llm_client = llm_client
        self.tools = tools
        self.workspace_root = workspace_root
        self.rule_providers = rule_providers or []
        self.max_task_retries = max_task_retries
        self.max_pipeline_retries = max_pipeline_retries
        self.graph_builder = RepoGraphBuilder()
        self.context_retriever = ContextRetriever()
        self._repo_graph: Optional[RepoGraph] = None

    def execute_story(self, story: Dict, repo_path: str) -> bool:
        """
        Execute a user story through the full Phase 3 pipeline.

        Args:
            story: User story dict (title, description, acceptance_criteria).
            repo_path: Path to the repository.

        Returns:
            True if all tasks completed successfully (feature complete).
        """
        story_id = story.get("story_id", "STORY-?")
        story_title = story.get("title", "Unknown")

        logger.info("PlanOrchestrator", f"Starting pipeline for [{story_id}]: {story_title}")

        # ── Step 0: Build/Update Repository Intelligence Graph ───────────
        logger.info("PlanOrchestrator", "Step 0: Building repository intelligence graph...")
        graph_path = os.path.join(self.workspace_root, "repo_graph.json")
        if self._repo_graph:
            self._repo_graph = self.graph_builder.incremental_update(repo_path, self._repo_graph)
        else:
            existing = self.graph_builder.load(graph_path)
            if existing:
                self._repo_graph = self.graph_builder.incremental_update(repo_path, existing)
            else:
                self._repo_graph = self.graph_builder.build(repo_path)
        self.graph_builder.save(self._repo_graph, graph_path)

        # ── Step 1: Generate Implementation Plan ─────────────────────────
        logger.info("PlanOrchestrator", "Step 1: Generating implementation plan...")
        planner = PlannerAgent(self.llm_client, self.tools)
        planning_context = {"repo_summary": self._repo_graph.summary()}
        plan = planner.plan(story, repo_path, context=planning_context)

        if not plan or not plan.tasks:
            logger.error("PlanOrchestrator", "Planning failed — no tasks generated.")
            return False

        logger.info("PlanOrchestrator", f"Plan '{plan.feature_title}' generated with {len(plan.tasks)} tasks")

        # ── Step 2: Build and Validate TaskGraph ─────────────────────────
        logger.info("PlanOrchestrator", "Step 2: Building task graph...")
        try:
            graph = TaskGraph(plan.tasks)
        except CycleError as e:
            logger.error("PlanOrchestrator", f"Task graph has a cycle: {e}")
            return False
        except ValueError as e:
            logger.error("PlanOrchestrator", f"Task graph has invalid dependencies: {e}")
            return False

        order = graph.topological_order()
        logger.info("PlanOrchestrator", "Execution order:")
        for i, task in enumerate(order, 1):
            logger.info("PlanOrchestrator", f"  {i}. [{task.task_id}] {task.title}")

        # ── Step 3: Schedule and Execute Tasks ───────────────────────────
        logger.info("PlanOrchestrator", "Step 3: Executing tasks...")
        engine = ExecutionEngine(
            llm_client=self.llm_client,
            workspace_root=os.path.join(self.workspace_root, f"plan_{plan.plan_id[:8]}"),
            rule_providers=self.rule_providers,
            max_pipeline_retries=self.max_pipeline_retries,
            context_retriever=self.context_retriever,
            repo_graph=self._repo_graph,
        )

        scheduler = TaskScheduler(graph, max_retries=self.max_task_retries)

        def task_executor(task: Task, run: RunExecution) -> bool:
            return engine.execute_task(task, repo_path, run)

        success = scheduler.run(task_executor)

        # ── Step 4: Report Result ────────────────────────────────────────
        if success:
            logger.success(f"Feature '{plan.feature_title}' completed — all {len(plan.tasks)} tasks passed.")
        else:
            failed = [t for t in graph.tasks if t.status.value == "failed"]
            logger.error("PlanOrchestrator", 
                        f"Feature '{plan.feature_title}' failed. "
                        f"Failed tasks: {[t.task_id for t in failed]}")

        return success

    def execute_stories(self, stories: List[Dict], repo_path: str) -> bool:
        """
        Execute a list of stories sequentially through the Phase 3 pipeline.

        Args:
            stories: List of user story dicts.
            repo_path: Path to the repository.

        Returns:
            True if all stories completed successfully.
        """
        if not isinstance(stories, list):
            stories = [stories]

        logger.info("PlanOrchestrator", f"Processing {len(stories)} stories via Phase 3 pipeline")

        for story in stories:
            story_id = story.get("story_id", "STORY-?")
            success = self.execute_story(story, repo_path)
            if not success:
                logger.error("PlanOrchestrator", f"Story [{story_id}] failed — aborting remaining stories.")
                return False

        logger.success("All stories completed successfully via Phase 3 pipeline.")
        return True
