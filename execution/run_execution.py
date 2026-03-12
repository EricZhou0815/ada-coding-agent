"""
execution/run_execution.py

Execution engine that runs a single Task through the CodingAgent + Verification pipeline.
Manages workspace setup, agent invocation, and result collection.
"""

import os
import shutil
import stat
from typing import Dict, Optional, List

from planning.models import Task, RunExecution, RunStatus, VerificationResult
from utils.logger import logger

# Late imports to avoid circular deps
_ContextRetriever = None
_RepoGraph = None


def _handle_remove_readonly(func, path, exc):
    """Error handler for Windows readonly file issues."""
    if func in (os.unlink, os.remove, os.rmdir):
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    else:
        raise


class ExecutionEngine:
    """
    Responsible for executing a single Task via the coding agent pipeline.

    Steps:
      1. Create isolated workspace (copy repo snapshot)
      2. Build task prompt from Task model
      3. Run CodingAgent → ValidationAgent pipeline
      4. Run QualityGate verification
      5. Copy results back on success
      6. Clean up workspace
    """

    def __init__(self, llm_client, workspace_root: str, rule_providers=None, max_pipeline_retries: int = 25, context_retriever=None, repo_graph=None):
        """
        Args:
            llm_client: LLM client instance.
            workspace_root: Root directory for task workspaces.
            rule_providers: Optional list of rule providers for validation.
            max_pipeline_retries: Max retries for the CodingAgent→Validation loop.
            context_retriever: Optional ContextRetriever for Phase 4 intelligence.
            repo_graph: Optional RepoGraph for Phase 4 intelligence.
        """
        self.llm_client = llm_client
        self.workspace_root = workspace_root
        self.rule_providers = rule_providers or []
        self.max_pipeline_retries = max_pipeline_retries
        self.context_retriever = context_retriever
        self.repo_graph = repo_graph

    def execute_task(self, task: Task, repo_path: str, run: RunExecution) -> bool:
        """
        Execute a single task in an isolated workspace.

        Args:
            task: The Task to execute.
            repo_path: Path to the current repo state.
            run: RunExecution tracking object.

        Returns:
            True if the task completed successfully, False otherwise.
        """
        # Create isolated workspace
        task_workspace = os.path.join(self.workspace_root, f"task_{task.task_id}")
        isolated_repo = os.path.join(task_workspace, "repo")

        run.workspace_path = task_workspace

        try:
            # Setup workspace
            self._setup_workspace(repo_path, isolated_repo)
            run.log(f"Workspace created at {task_workspace}")

            # Convert task to story format for the existing pipeline
            story = self._task_to_story(task)

            # Retrieve intelligent context if available
            intel_context = None
            if self.context_retriever and self.repo_graph:
                try:
                    intel_context = self.context_retriever.get_context(
                        f"{task.title}: {task.description}", self.repo_graph
                    )
                    run.log(f"Intelligence context: {len(intel_context.relevant_files)} relevant files")
                except Exception as e:
                    run.log(f"Intelligence context retrieval failed (non-fatal): {e}")

            # Execute via PipelineOrchestrator
            success = self._run_pipeline(story, isolated_repo, task_workspace, intel_context=intel_context)

            if success:
                # Run quality gate verification
                verification = self._run_quality_gate(task, isolated_repo)
                run.result = verification

                if verification.validation_passed:
                    # Copy results back
                    self._copy_results_back(isolated_repo, repo_path)
                    run.log("Results copied back to repo")
                    return True
                else:
                    run.log(f"Quality gate failed: {verification.details}")
                    return False
            else:
                run.log("Pipeline execution failed")
                return False

        except Exception as e:
            run.log(f"Execution error: {e}")
            logger.error("ExecutionEngine", f"Task '{task.task_id}' failed: {e}")
            return False

        finally:
            self._cleanup_workspace(task_workspace)

    def _setup_workspace(self, repo_path: str, isolated_repo: str) -> None:
        """Create isolated workspace by copying repo snapshot."""
        os.makedirs(os.path.dirname(isolated_repo), exist_ok=True)
        if os.path.exists(isolated_repo):
            shutil.rmtree(isolated_repo, onexc=_handle_remove_readonly)
        shutil.copytree(repo_path, isolated_repo)

    def _task_to_story(self, task: Task) -> Dict:
        """Convert a Task model to the story dict format expected by the existing pipeline."""
        return {
            "story_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": task.success_criteria,
        }

    def _run_pipeline(self, story: Dict, isolated_repo: str, task_workspace: str, intel_context=None) -> bool:
        """Run the CodingAgent→ValidationAgent pipeline."""
        from agents.coding_agent import CodingAgent
        from config import Config
        from orchestrator.task_executor import PipelineOrchestrator
        from orchestrator.rule_provider import LocalFolderRuleProvider
        from isolation.sandbox import SandboxedTools

        tools = SandboxedTools(isolated_repo)
        llm_client = Config.get_llm_client()

        coding_agent = CodingAgent(llm_client, tools)
        agents_pipeline = [coding_agent]

        rule_providers = self.rule_providers or [LocalFolderRuleProvider()]
        executor = PipelineOrchestrator(
            agents_pipeline,
            rule_providers=rule_providers,
            max_retries=self.max_pipeline_retries,
        )

        checkpoint_path = os.path.join(task_workspace, "checkpoint.json")
        additional_context = {"checkpoint_path": checkpoint_path}

        # Inject intelligence context if available
        if intel_context:
            additional_context["repo_intelligence"] = intel_context.to_prompt_context()

        return executor.execute_story(story, isolated_repo, additional_context=additional_context)

    def _run_quality_gate(self, task: Task, repo_path: str) -> VerificationResult:
        """
        Run deterministic verification checks.
        Falls back to all-pass if no verification commands are detected.
        """
        from verification.quality_gate import QualityGate
        gate = QualityGate(repo_path)
        return gate.verify(task)

    def _copy_results_back(self, isolated_repo: str, original_repo: str) -> None:
        """Copy modified files from isolated workspace back to original repo."""
        for item in os.listdir(isolated_repo):
            src = os.path.join(isolated_repo, item)
            dst = os.path.join(original_repo, item)

            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst, onexc=_handle_remove_readonly)
                shutil.copytree(src, dst)

    def _cleanup_workspace(self, workspace: str) -> None:
        """Remove task workspace."""
        if os.path.exists(workspace):
            try:
                shutil.rmtree(workspace, onexc=_handle_remove_readonly)
            except Exception as e:
                logger.warning("ExecutionEngine", f"Cleanup failed: {e}")
