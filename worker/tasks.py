import os
import json
import shutil
import logging
from pathlib import Path
from celery import Celery
from typing import Optional

# Load env variables since tasks run isolated
from dotenv import load_dotenv
load_dotenv()

# Setup Celery
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("ada_tasks", broker=redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4"))
)

# Redis client for retry tracking
import redis
redis_client = redis.from_url(redis_url)

# Max retry attempts for CI fixes
MAX_CI_FIX_RETRIES = 3
CI_RETRY_KEY_TTL = 3600  # 1 hour

from utils.logger import logger as ada_logger

def _append_job_log(job_id, message):
    """Legacy helper, redirects to structured logger info."""
    ada_logger.set_job_id(job_id)
    ada_logger.info("System", message)
    
def _update_job_status(job_id, status):
    """Utility to update DB status."""
    from api.database import SessionLocal, StoryJob
    db = SessionLocal()
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    if job:
        job.status = status
        db.commit()
    db.close()


# ── Common Task Helpers ─────────────────────────────────────────────────────

def _create_workspace(prefix: str) -> Path:
    """
    Create an isolated workspace directory for task execution.
    
    Args:
        prefix: Prefix for the workspace directory name
        
    Returns:
        Path to the created workspace directory
    """
    base_tmp = Path(os.getenv("ADA_TMP_DIR", "/tmp/ada_runs")).resolve()
    workspace_dir = base_tmp / prefix
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def _execute_coding_task(
    repo_url: str,
    branch_name: str,
    task_definition: dict,
    workspace_dir: Path,
    logger: logging.Logger
) -> tuple[bool, bool, Optional['GitManager']]:
    """
    Common workflow for agent-based tasks:
    1. Clone repository and checkout target branch
    2. Initialize CodingAgent with LLM and Tools
    3. Execute the task
    4. Return results
    
    Args:
        repo_url: Repository URL to clone
        branch_name: Branch to checkout
        task_definition: Task dict with title, description, acceptance_criteria
        workspace_dir: Workspace directory for the operation
        logger: Logger instance for this task
        
    Returns:
        Tuple of (agent_success, has_changes, git_manager)
        Returns (False, False, None) on error
    """
    from tools.git_manager import GitManager
    from tools.tools import Tools
    from config import Config
    from agents.coding_agent import CodingAgent
    
    try:
        # Extract repo name from URL
        repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
        repo_path = str(workspace_dir / repo_name)
        
        # Clone and checkout
        logger.info(f"Cloning {repo_url} to {repo_path}")
        git = GitManager.clone(repo_url, repo_path)
        git.checkout(branch_name)
        
        # Initialize CodingAgent
        llm = Config.get_llm_client()
        coding_agent = CodingAgent(llm, Tools())
        
        # Execute task
        logger.info(f"Running CodingAgent on task: {task_definition['title']}")
        result = coding_agent.run(task_definition, repo_path, context={})
        
        has_changes = git.has_changes()
        logger.info(f"Task completed. Success: {result.success}, Has changes: {has_changes}")
        
        return result.success, has_changes, git
        
    except Exception as e:
        logger.exception(f"Error during coding task execution: {e}")
        return False, False, None


@celery_app.task(bind=True)
def execute_sdlc_story(self, job_id: str, repo_url: str, story: dict, use_mock: bool = False):
    """
    Celery task that executes a specific story in complete workspace isolation.
    """
    import sys
    
    # We lazily import Ada internals here so Celery workers can spawn fast
    # and they import config from env perfectly
    from config import Config
    from tools.tools import Tools
    from orchestrator.sdlc_orchestrator import SDLCOrchestrator
    from orchestrator.rule_provider import LocalFolderRuleProvider
    
    from utils.logger import logger
    logger.set_job_id(job_id)
    
    _update_job_status(job_id, "RUNNING")
    logger.info("System", f"Initializing isolated run for {repo_url}...")
    
    # Generate unique sandbox folder
    # /tmp/ada_runs/1234-5678-uuid/
    base_tmp = Path(os.getenv("ADA_TMP_DIR", "/tmp/ada_runs")).resolve()
    workspace_dir = base_tmp / job_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Construct isolated Ada components
        llm_client = Config.get_llm_client(force_mock=use_mock)
        planning_tools = Tools()
        rule_providers = [LocalFolderRuleProvider()]
        
        # All task outputs (`STORY-T1.json`, etc) should be saved IN the temp workspace, not globally
        tasks_output_dir = str(workspace_dir / "tasks_output")
        
        orchestrator = SDLCOrchestrator(
            llm_client=llm_client,
            tools=planning_tools,
            repo_url=repo_url,
            base_branch="main", # Should be configurable in future
            tasks_output_dir=tasks_output_dir,
            rule_providers=rule_providers
        )
        
        _append_job_log(job_id, f"Cloning and processing story: {story.get('title', 'Unknown')}")
        
        # RUN THE SDLC! Always force clean to release disk space in celery container.
        success = orchestrator.run([story], workspace_dir=str(workspace_dir), clean_workspace=True)
        
        if success:
            _append_job_log(job_id, "PR successfully generated and pushed.")
            status = "SUCCESS"
        else:
            _append_job_log(job_id, "Execution failed or partially succeeded (Draft PR).")
            status = "FAILED"
            
        _update_job_status(job_id, status)
        return status
        
    except Exception as e:
        logger.error("System", f"Fatal error in Ada run {job_id}: {e}")
        _append_job_log(job_id, f"Fatal error: {str(e)}")
        _update_job_status(job_id, "FAILED")
        
        # Cleanup aggressively on crash
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)
            
        return "FAILED"