import os
import json
from uuid import uuid4
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional, Generator
import redis
import asyncio
from fastapi.responses import StreamingResponse

from api.database import SessionLocal, StoryJob, get_db
from api.webhooks import vcs as vcs_webhooks

# In production, we drop tasks directly into Redis via Celery
from worker.tasks import execute_sdlc_story

app = FastAPI(
    title="Ada Autonomous Agent API",
    description="Scalable, isolated, multi-tenant AI developer for user stories.",
    version="1.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
    logs: List[Dict[str, str]]
    created_at: str

# ── Endpoints ───────────────────────────────────────────────────────────────

app.include_router(vcs_webhooks.router, prefix="/api/v1/webhooks")

@app.post("/api/v1/execute", response_model=List[JobResponse])
def execute_stories(req: ExecutionRequest, db: SessionLocal = Depends(get_db)):
    """
    Submits one or more user stories to the Ada execution queue.
    Each story gets its own isolated sandbox execution.
    """
    jobs_created = []
    
    for story in req.stories:
        job_id = str(uuid4())
        
        # 1. Create Job Entry in Database
        new_job = StoryJob(
            id=job_id,
            repo_url=str(req.repo_url),
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


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: SessionLocal = Depends(get_db)):
    """
    Check the status and logs of a running story job. 
    Can be polled by the frontend.
    """
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    logs = []
    try:
        logs = json.loads(job.logs) if job.logs else []
    except:
        pass
        
    return {
        "job_id": job.id,
        "status": job.status,
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
    return {"status": "healthy"}
