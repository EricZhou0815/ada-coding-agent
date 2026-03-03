import os
import json
from uuid import uuid4
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional, Generator
import redis
import asyncio
from fastapi.responses import StreamingResponse

from api.database import SessionLocal, StoryJob, get_db
from api.webhooks import vcs as vcs_webhooks
from config import Config

# In production, we drop tasks directly into Redis via Celery
from worker.tasks import execute_sdlc_story

app = FastAPI(
    title="Ada Autonomous Agent API",
    description="Scalable, isolated, multi-tenant AI developer for user stories.",
    version=Config.get_app_version()
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://0.0.0.0:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ──────────────────────────────────────────────────────────────────
class StoryPayload(BaseModel):
    title: str
    story_id: str
    acceptance_criteria: List[str]
    description: Optional[str] = ""

class ExecutionRequest(BaseModel):
    repo_url: HttpUrl
    stories: List[StoryPayload]
    base_branch: Optional[str] = "main"
    use_mock: bool = False
    
class JobResponse(BaseModel):
    job_id: str
    status: str
    repo_url: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    repo_url: str
    story_title: Optional[str]
    logs: List[Dict[str, Any]]
    created_at: str

class JobSummary(BaseModel):
    job_id: str
    status: str
    repo_url: str
    story_title: Optional[str]
    created_at: str

# ── Security Dependencies ───────────────────────────────────────────────────

async def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")):
    """
    Verify API key from X-Api-Key header.
    
    Keys are configured via API_KEYS environment variable (comma-separated).
    Example: API_KEYS=key1,key2,key3
    
    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    valid_keys_str = os.getenv("API_KEYS", "")
    if not valid_keys_str:
        # No keys configured - security risk! Log warning but allow in dev
        # In production, this should fail hard
        import logging
        logging.warning("⚠️  API_KEYS not configured - API authentication is DISABLED")
        return "dev-mode-no-auth"
    
    valid_keys = [k.strip() for k in valid_keys_str.split(",") if k.strip()]
    
    if not x_api_key or x_api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide valid X-Api-Key header."
        )
    
    return x_api_key

# ── Endpoints ───────────────────────────────────────────────────────────────

app.include_router(vcs_webhooks.router, prefix="/api/v1/webhooks")

@app.post("/api/v1/execute", response_model=List[JobResponse])
def execute_stories(
    req: ExecutionRequest,
    db: SessionLocal = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Submits one or more user stories to the Ada execution queue.
    Each story gets its own isolated sandbox execution.
    
    **Authentication Required:** Provide X-Api-Key header with valid API key.
    """
    jobs_created = []
    
    for story in req.stories:
        job_id = str(uuid4())
        
        # 1. Create Job Entry in Database
        new_job = StoryJob(
            id=job_id,
            repo_url=str(req.repo_url),
            story_title=story.title,
            status="PENDING",
            logs=json.dumps([{"timestamp": "now", "message": "Job queued for celery worker."}])
        )
        db.add(new_job)
        jobs_created.append({
            "job_id": job_id,
            "repo_url": str(req.repo_url),
            "status": "QUEUED"
        })
        
        # Commit DB first to avoid race condition with the Celery worker
        db.commit()
        
        # 2. Dispatch Async Celery Task
        execute_sdlc_story.delay(
            job_id=job_id, 
            repo_url=str(req.repo_url), 
            story=story.model_dump(),
            use_mock=req.use_mock
        )
        
    return jobs_created


@app.get("/api/v1/jobs", response_model=List[JobSummary])
def list_jobs(db: SessionLocal = Depends(get_db)):
    """
    Returns a history of all user story jobs.
    """
    jobs = db.query(StoryJob).order_by(StoryJob.created_at.desc()).all()
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "repo_url": j.repo_url,
            "story_title": j.story_title,
            "created_at": str(j.created_at)
        } for j in jobs
    ]

@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str, 
    db: SessionLocal = Depends(get_db),
    limit: int = 100,
    offset: int = 0
):
    """
    Check the status and logs of a running story job. 
    Can be polled by the frontend.
    
    Query parameters:
    - limit: Maximum number of logs to return (default: 100)
    - offset: Number of logs to skip for pagination (default: 0)
    """
    from api.database import JobLog
    
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Query logs from new job_logs table, ordered by timestamp descending
    log_entries = db.query(JobLog).filter(
        JobLog.job_id == job_id
    ).order_by(
        JobLog.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    # Convert to API format
    logs = [
        {
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "level": log.level,
            "prefix": log.prefix,
            "message": log.message,
            "metadata": log.meta or {}
        }
        for log in reversed(log_entries)  # Reverse to get chronological order
    ]
    
    # Fallback: If no logs in new table, try legacy JSON format (for backwards compatibility)
    if not logs and job.logs:
        try:
            logs = json.loads(job.logs) if job.logs else []
        except:
            pass
        
    return {
        "job_id": job.id,
        "status": job.status,
        "repo_url": job.repo_url,
        "story_title": job.story_title,
        "logs": logs,
        "created_at": str(job.created_at)
    }

@app.get("/api/v1/jobs/{job_id}/stream")
async def stream_job_logs(job_id: str):
    """
    SSE endpoint to stream live logs from Redis Pub/Sub.
    """
    def redis_event_generator():
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe(f"logs:{job_id}")
        
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    yield f"data: {data}\n\n"
        finally:
            pubsub.unsubscribe(f"logs:{job_id}")
            pubsub.close()

    return StreamingResponse(redis_event_generator(), media_type="text/event-stream")

@app.get("/health")
def health_check():
    """Simple healthcheck for ECS Target Groups"""
    return {
        "status": "healthy",
        "version": Config.get_app_version()
    }
