import os
from pathlib import Path
from typing import List, Dict, Optional
from orchestrator.rule_provider import RuleProvider
from utils.logger import logger
from config import Config

class EpicOrchestrator:
    """
    Higher-level orchestrator that executes User Stories directly.
    It bypasses the planning phase and instructs the CodingAgent to handle the full story.
    """

    def __init__(self, llm_client, tools, tasks_output_dir: str = "tasks", rule_providers: Optional[List[RuleProvider]] = None):
        """
        Args:
            llm_client: LLM client instance.
            tools: Read-only tools for initial exploration.
            tasks_output_dir: (Deprecated) Kept for signature compatibility.
            rule_providers: Optional list of RuleProviders passed into each Sandbox execution.
        """
        self.llm_client = llm_client
        self.tools = tools
        self.rule_providers = rule_providers or []

    def execute_stories(self, stories: List[Dict], repo_path: str) -> bool:
        """
        Executes an entire backlog of User Stories end-to-end, sequentially.
        
        For each story:
          The story is executed directly inside an isolated SandboxBackend.
          The sandbox copies results back to repo_path so subsequent stories
          see the updated codebase.

        Args:
            stories: List of user story dicts (or a single story dict).
            repo_path: The repository path that will be modified.

        Returns:
            True if all stories completed successfully.
        """
        if not isinstance(stories, list):
            stories = [stories]

        logger.info("EpicOrchestrator", f"🚀 Processing {len(stories)} User Stories in Direct-Execution Mode")

        for story in stories:
            story_id = story.get("story_id", "STORY-?")
            logger.info("EpicOrchestrator", f"\n{'='*70}\n📖 Story [{story_id}]: {story.get('title', 'Unknown')}\n{'='*70}")

            success = self._run_story_in_sandbox(story, repo_path)
            if not success:
                logger.error("EpicOrchestrator", f"Story [{story_id}] failed. Aborting backlog.")
                return False

        logger.success("All User Stories completed successfully. ✅")
        return True

    def _run_story_in_sandbox(self, story: Dict, repo_path: str) -> bool:
        """
        Spins up a fresh isolation backend for a single story and executes it.
        """
        # Isolate the sandbox root inside the current workspace (parent of repo_path) to prevent global collisions
        sandbox_root = os.path.join(os.path.dirname(os.path.abspath(repo_path)), ".sandbox")
        
        # Call the generic isolation backend (Sandbox, Docker, or ECS)
        backend = Config.get_isolation_backend(workspace_root=sandbox_root)
        
        logger.info("EpicOrchestrator", f"Using isolation backend: {backend.get_name()}")
        
        try:
            backend.setup(story, repo_path)
            success = backend.execute(story, repo_path)
            return success
        finally:
            backend.cleanup()
