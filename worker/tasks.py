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
