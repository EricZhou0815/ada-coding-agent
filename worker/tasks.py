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
# Extract shared patterns between fix_ci_failure and apply_pr_feedback

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
@celery_app.task(bind=True)
def fix_ci_failure(self, repo_url: str, owner: str, repo: str, branch_name: str, run_id: int):
    """
    Surgical worker task: Wakes up when CI fails, reads the logs, and tries to patch the code.
    Includes retry limiting to prevent infinite fix loops.
    """
    from config import Config
    
    logger = logging.getLogger("CeleryFixTask")
    logger.info(f"Initiating CI Fix for branch: {branch_name} on repo: {owner}/{repo}")
    
    vcs = Config.get_vcs_client()
    
    # Find PR number for this branch (needed for comments)
    pr_number = None
    try:
        prs = vcs.get_pull_requests(owner, repo)
        pr_number = next((p["number"] for p in prs if p["head"]["ref"] == branch_name), None)
    except Exception as e:
        logger.warning(f"Could not find PR for branch {branch_name}: {e}")
    
    # Check retry count
    retry_key = f"ada:ci_fix:{owner}/{repo}:{branch_name}"
    current_retries = int(redis_client.get(retry_key) or 0)
    
    if current_retries >= MAX_CI_FIX_RETRIES:
        logger.warning(f"Max CI fix retries ({MAX_CI_FIX_RETRIES}) reached for {branch_name}")
        if pr_number:
            vcs.create_issue_comment(
                owner, repo, pr_number,
                f"⚠️ **Ada:** I've attempted to fix CI failures **{MAX_CI_FIX_RETRIES} times** but tests are still failing.\n\n"
                f"This may require human review. Some possible reasons:\n"
                f"- The issue is in the test environment, not the code\n"
                f"- The fix requires changes I'm not confident making\n"
                f"- There's a flaky test or infrastructure issue\n\n"
                f"Please review the CI logs and let me know if you'd like me to try a specific approach.\n"
                f"Use `@ada-ai reset ci` to reset my retry counter if you'd like me to try again."
            )
        return "MAX_RETRIES_EXCEEDED"
    
    # Increment retry counter
    redis_client.setex(retry_key, CI_RETRY_KEY_TTL, current_retries + 1)
    logger.info(f"CI fix attempt {current_retries + 1}/{MAX_CI_FIX_RETRIES} for {branch_name}")
    
    # Fetch failing CI logs
    try:
        jobs_data = vcs.get_pipeline_jobs(owner, repo, run_id)
        failed_jobs = [j for j in jobs_data.get("jobs", []) if j.get("conclusion") == "failure"]
        
        all_logs = []
        for job in failed_jobs:
            job_name = job.get("name", "Unknown Job")
            logs = vcs.get_job_logs(owner, repo, job.get("id"))
            all_logs.append(f"--- FAILED JOB: {job_name} ---\n{logs}")
        
        ci_logs = "\n\n".join(all_logs)
        if not ci_logs:
            ci_logs = "No detailed logs found for the failed jobs."
        
        # Truncate logs if too long for the LLM context (last 20k characters)
        if len(ci_logs) > 20000:
            ci_logs = "...[TRUNCATED]...\n" + ci_logs[-20000:]
            
    except Exception as e:
        logger.error(f"Failed to fetch CI logs: {e}")
        ci_logs = f"Error fetching logs via GitHub API: {str(e)}"

    # Create isolated workspace
    workspace_dir = _create_workspace(f"fix_{run_id}")
    
    try:
        # Build task definition
        task = {
            "title": f"Fix CI Pipeline Failure on {branch_name}",
            "description": f"The CI test suite just failed (attempt {current_retries + 1}/{MAX_CI_FIX_RETRIES}). Here are the logs for the failed jobs:\n\n{ci_logs}\n\nPlease analyze the logs, find the bug in the code, and fix it.",
            "acceptance_criteria": ["The bug causing the CI failure is resolved."]
        }
        
        # Execute coding task using common helper
        success, has_changes, git = _execute_coding_task(
            repo_url, branch_name, task, workspace_dir, logger
        )
        
        # Handle results
        if success and has_changes and git:
            git.commit("fix: resolve continuous integration test failures")
            git.push(branch_name)
            logger.info(f"Pushed CI fix for {branch_name} successfully!")
            
            if pr_number:
                vcs.create_issue_comment(
                    owner, repo, pr_number,
                    f"🔧 **Ada:** I've pushed a fix for the CI failure (attempt {current_retries + 1}).\n\n"
                    f"The CI pipeline should restart automatically. If it fails again, I'll take another look."
                )
            
            return "SUCCESS"
        else:
            logger.warning("CodingAgent did not produce changes or reported failure.")
            if pr_number:
                vcs.create_issue_comment(
                    owner, repo, pr_number,
                    f"🤔 **Ada:** I analyzed the CI failure but couldn't determine a fix (attempt {current_retries + 1}/{MAX_CI_FIX_RETRIES}).\n\n"
                    f"I'll try again if CI fails on the next run, or you can provide hints with `@ada-ai <suggestion>`."
                )
            return "NO_CHANGES"
            
    except Exception as e:
        logger.exception(f"Error during CI fix attempt: {e}")
        if pr_number:
            vcs.create_issue_comment(
                owner, repo, pr_number,
                f"❌ **Ada:** I encountered an error while trying to fix CI (attempt {current_retries + 1}/{MAX_CI_FIX_RETRIES}):\n\n```\n{str(e)[:500]}\n```"
            )
        return "ERROR"
            
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)

@celery_app.task(bind=True)
def apply_pr_feedback(self, repo_url: str, owner: str, repo: str, pr_number: int, feedback: str):
    """
    Surgical worker task: Applies human engineer code-review feedback to a PR.
    Includes detailed feedback about what was changed.
    """
    from config import Config

    logger = logging.getLogger("CeleryFeedbackTask")
    logger.info(f"Applying Human Feedback on PR #{pr_number}")
    
    vcs = Config.get_vcs_client()
    
    # Fetch PR details to get branch name
    try:
        pr_data = vcs.get_pull_request(owner, repo, pr_number)
        branch_name = pr_data["head"]["ref"]
    except Exception as e:
        logger.error(f"Failed to fetch PR data: {e}")
        vcs.create_issue_comment(
            owner, repo, pr_number,
            f"❌ **Ada:** I couldn't fetch the PR details to apply your feedback:\n\n```\n{str(e)[:300]}\n```"
        )
        return "ERROR"

    # Create isolated workspace
    workspace_dir = _create_workspace(f"feedback_{pr_number}")
    
    try:
        # Build task definition
        task = {
            "title": f"Apply Feedback on PR #{pr_number}",
            "description": f"An engineer has reviewed your PR and requested changes:\n\n> {feedback}\n\nPlease apply these changes.",
            "acceptance_criteria": ["All requested feedback has been implemented."]
        }
        
        # Execute coding task using common helper
        success, has_changes, git = _execute_coding_task(
            repo_url, branch_name, task, workspace_dir, logger
        )
        
        # Handle results
        if success and has_changes and git:
            # Get summary of changes before committing
            changes_summary = git.get_diff_summary() if hasattr(git, 'get_diff_summary') else ""
            
            git.commit(f"chore: apply code review feedback from PR #{pr_number}")
            git.push(branch_name)
            
            response = "✅ **Ada:** I've applied your feedback and pushed the changes.\n\n"
            if changes_summary:
                response += f"**Changes made:**\n```\n{changes_summary[:1000]}\n```\n\n"
            response += "Please review and let me know if you'd like any adjustments!"
            
            vcs.create_issue_comment(owner, repo, pr_number, response)
            return "SUCCESS"
        elif success and not has_changes:
            vcs.create_issue_comment(
                owner, repo, pr_number,
                "🤔 **Ada:** I analyzed your feedback but didn't find any code changes to make.\n\n"
                "Possible reasons:\n"
                "- The requested change may already be in place\n"
                "- I may have misunderstood the feedback\n\n"
                "Could you clarify what you'd like me to change? For example: `@ada-ai Please rename the variable 'x' to 'count' in utils.py`"
            )
            return "NO_CHANGES"
        else:
            vcs.create_issue_comment(
                owner, repo, pr_number,
                "❌ **Ada:** I tried to apply your feedback but encountered issues.\n\n"
                "This might be because:\n"
                "- The feedback requires changes I'm not confident making\n"
                "- There's ambiguity in what needs to be changed\n\n"
                "Could you provide more specific instructions? For example:\n"
                "- Which file(s) to modify\n"
                "- The exact change you'd like to see"
            )
            return "FAILED"
            
    except Exception as e:
        logger.exception(f"Error applying PR feedback: {e}")
        vcs.create_issue_comment(
            owner, repo, pr_number,
            f"❌ **Ada:** I encountered an error while trying to apply your feedback:\n\n```\n{str(e)[:500]}\n```\n\n"
            "Please try again or provide alternative instructions."
        )
        return "ERROR"
            
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


# ── Planning Agent Tasks ────────────────────────────────────────────────────

@celery_app.task(bind=True)
def process_planning_batch(self, batch_id: str, repo_url: str, inputs: list, planning_mode: str, auto_execute: bool):
    """
    Process a planning batch asynchronously.
    
    Creates planning sessions for each input and processes them based on mode:
    - Sequential: Activate and process one session at a time
    - Parallel: Activate all sessions (processed when messages arrive)
    
    Args:
        batch_id: Planning batch ID (already created in DB)
        repo_url: Repository URL for execution
        inputs: List of user requests
        planning_mode: "sequential" or "parallel"
        auto_execute: Whether to auto-queue completed stories
    """
    from api.database import SessionLocal, PlanningBatch
    from agents.planning_service import PlanningService
    from config import Config
    import asyncio
    
    db = SessionLocal()
    
    try:
        # Update batch status
        batch = db.query(PlanningBatch).filter(PlanningBatch.id == batch_id).first()
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        
        batch.status = "PROCESSING"
        batch.celery_task_id = self.request.id
        db.commit()
        
        # Initialize planning service
        llm_client = Config.get_async_llm_client()
        service = PlanningService(llm_client)
        
        # Process batch (this will create sessions and activate them)
        # Use asyncio to run the async method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            batch_result, execution_jobs = loop.run_until_complete(
                service.create_batch(
                    db=db,
                    repo_url=repo_url,
                    inputs=inputs,
                    planning_mode=planning_mode,
                    auto_execute=auto_execute
                )
            )
        finally:
            loop.close()
        
        # Update batch status to complete
        batch.status = "COMPLETE"
        db.commit()
        
        ada_logger.success("PlanningWorker", f"Batch {batch_id} processed: {len(batch.sessions)} sessions, {len(execution_jobs)} jobs")
        
        return {
            "batch_id": batch_id,
            "sessions_created": len(batch.sessions),
            "execution_jobs": execution_jobs,
            "status": "COMPLETE"
        }
        
    except Exception as e:
        ada_logger.error("PlanningWorker", f"Error processing batch {batch_id}: {e}")
        
        # Update batch status to failed
        batch = db.query(PlanningBatch).filter(PlanningBatch.id == batch_id).first()
        if batch:
            batch.status = "FAILED"
            batch.error_message = str(e)
            db.commit()
        
        raise
        
    finally:
        db.close()


@celery_app.task(bind=True)
def process_planning_message(self, session_id: str, message: str):
    """
    Process a single message in a planning session asynchronously.
    
    Args:
        session_id: Planning session ID
        message: User's message (answer to question)
        
    Returns:
        Updated session data
    """
    from api.database import SessionLocal, PlanningSession
    from agents.planning_service import PlanningService
    from config import Config
    import asyncio
    
    db = SessionLocal()
    
    try:
        # Initialize planning service
        llm_client = Config.get_async_llm_client()
        service = PlanningService(llm_client)
        
        # Process message asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                service.process_message(
                    db=db,
                    session_id=session_id,
                    message=message
                )
            )
        finally:
            loop.close()
        
        ada_logger.info("PlanningWorker", f"Session {session_id} message processed: state={session.state}")
        
        return {
            "session_id": session.id,
            "state": session.state,
            "current_question": session.current_question,
            "iteration": session.iteration,
            "story_result": session.story_result,
            "execution_job_id": session.execution_job_id
        }
        
    except Exception as e:
        ada_logger.error("PlanningWorker", f"Error processing message in session {session_id}: {e}")
        raise
        
    finally:
        db.close()

