import os
import json
import shutil
import logging
from pathlib import Path
from celery import Celery

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

def _append_job_log(job_id, message):
    """Utility to append logs to the DB."""
    from api.database import SessionLocal, StoryJob
    from datetime import datetime
    
    db = SessionLocal()
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    if job:
        try:
            logs = json.loads(job.logs) if job.logs else []
        except:
            logs = []
        logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "message": message
        })
        job.logs = json.dumps(logs)
        db.commit()
    db.close()
    
def _update_job_status(job_id, status):
    """Utility to update DB status."""
    from api.database import SessionLocal, StoryJob
    db = SessionLocal()
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    if job:
        job.status = status
        db.commit()
    db.close()


@celery_app.task(bind=True)
def execute_sdlc_story(self, job_id: str, repo_url: str, story: dict):
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
    
    logger = logging.getLogger("CeleryTask")
    
    _update_job_status(job_id, "RUNNING")
    _append_job_log(job_id, f"Initializing isolated run for {repo_url}...")
    
    # Generate unique sandbox folder
    # /tmp/ada_runs/1234-5678-uuid/
    base_tmp = Path(os.getenv("ADA_TMP_DIR", "/tmp/ada_runs")).resolve()
    workspace_dir = base_tmp / job_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Construct isolated Ada components
        llm_client = Config.get_llm_client()
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
        logger.exception(f"Fatal error in Ada run {job_id}")
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
    """
    from tools.github_client import GitHubClient
    from tools.git_manager import GitManager
    from tools.tools import Tools
    from config import Config
    from agents.coding_agent import CodingAgent
    
    logger = logging.getLogger("CeleryFixTask")
    logger.info(f"Initiating CI Fix for branch: {branch_name} on repo: {owner}/{repo}")
    
    gh = GitHubClient()
    
    # 1. Fetch failing logs
    try:
        jobs_data = gh.get_run_jobs(owner, repo, run_id)
        failed_jobs = [j for j in jobs_data.get("jobs", []) if j.get("conclusion") == "failure"]
        
        all_logs = []
        for job in failed_jobs:
            job_name = job.get("name", "Unknown Job")
            logs = gh.get_job_logs(owner, repo, job.get("id"))
            all_logs.append(f"--- FAILED JOB: {job_name} ---\n{logs}")
        
        ci_logs = "\n\n".join(all_logs)
        if not ci_logs:
            ci_logs = "No detailed logs found for the failed jobs."
        
        # Truncate logs if too long for the LLM context (e.g., last 20k characters)
        if len(ci_logs) > 20000:
            ci_logs = "...[TRUNCATED]...\n" + ci_logs[-20000:]
            
    except Exception as e:
        logger.error(f"Failed to fetch CI logs: {e}")
        ci_logs = f"Error fetching logs via GitHub API: {str(e)}"

    # 2. Create isolated /tmp/ folder
    base_tmp = Path(os.getenv("ADA_TMP_DIR", "/tmp/ada_runs")).resolve()
    workspace_dir = base_tmp / f"fix_{run_id}"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 3. Clone repo, but checkout the broken branch
        repo_path = str(workspace_dir / repo)
        git = GitManager.clone(repo_url, repo_path)
        git.checkout(branch_name)
        
        # 4. Initialize the CodingAgent
        llm = Config.get_llm_client()
        coding_agent = CodingAgent(llm, Tools())
        
        # 5. Formulate a targeted task
        task = {
            "title": f"Fix CI Pipeline Failure on {branch_name}",
            "description": f"The CI test suite just failed. Here are the logs for the failed jobs:\n\n{ci_logs}\n\nPlease analyze the logs, find the bug in the code, and fix it.",
            "acceptance_criteria": ["The bug causing the CI failure is resolved."]
        }
        
        # 6. Run the agent natively on the codebase
        result = coding_agent.run(task, repo_path, context={})
        
        # 7. Push the fix
        if result.success:
            git.commit("fix: resolve continuous integration test failures")
            git.push(branch_name)
            logger.info(f"Pushed CI fix for {branch_name} successfully!")
            
            # Leave a friendly comment on the PR (Optional: we'd need the PR number)
            # Find PR number for branch
            prs = gh.get_pull_requests(owner, repo)
            pr_number = next((p["number"] for p in prs if p["head"]["ref"] == branch_name), None)
            if pr_number:
                gh.create_issue_comment(owner, repo, pr_number, "🤖 **Ada Update:** I detected a CI failure and pushed a fix. Tests should restart automatically.")
            
            return "SUCCESS"
        else:
            logger.error("CodingAgent failed to generate a fix.")
            return "FAILED"
            
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)

@celery_app.task(bind=True)
def apply_pr_feedback(self, repo_url: str, owner: str, repo: str, pr_number: int, feedback: str):
    """
    Surgical worker task: Applies human engineer code-review feedback to a PR.
    """
    from tools.github_client import GitHubClient
    from tools.git_manager import GitManager
    from tools.tools import Tools
    from config import Config
    from agents.coding_agent import CodingAgent

    logger = logging.getLogger("CeleryFeedbackTask")
    logger.info(f"Applying Human Feedback on PR #{pr_number}")
    
    gh = GitHubClient()
    
    # 1. Fetch PR details to get branch name
    pr_data = gh.get_pull_request(owner, repo, pr_number)
    branch_name = pr_data["head"]["ref"]

    # 2. Create isolated /tmp/ folder
    base_tmp = Path(os.getenv("ADA_TMP_DIR", "/tmp/ada_runs")).resolve()
    workspace_dir = base_tmp / f"feedback_{pr_number}"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 3. Clone and checkout
        repo_path = str(workspace_dir / repo)
        git = GitManager.clone(repo_url, repo_path)
        git.checkout(branch_name)
        
        # 4. Initialize CodingAgent
        llm = Config.get_llm_client()
        coding_agent = CodingAgent(llm, Tools())
        
        # 5. Build task
        task = {
            "title": f"Apply Feedback on PR #{pr_number}",
            "description": f"An engineer has reviewed your PR and requested changes:\n\n> {feedback}\n\nPlease apply these changes.",
            "acceptance_criteria": ["All requested feedback has been implemented."]
        }
        
        # 6. Run
        result = coding_agent.run(task, repo_path, context={})
        
        if result.success:
            git.commit(f"chore: apply code review feedback from PR #{pr_number}")
            git.push(branch_name)
            gh.create_issue_comment(owner, repo, pr_number, "🤖 **Ada Update:** I've applied the feedback you provided. Please let me know if there's anything else!")
            return "SUCCESS"
        else:
            return "FAILED"
            
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)
