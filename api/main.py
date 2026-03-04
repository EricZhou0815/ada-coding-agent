import os
import json
from uuid import uuid4
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Header, Query
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

async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    api_key_query: Optional[str] = Query(None, alias="api_key")
):
    """
    Verify API key from X-Api-Key header or api_key query parameter.
    
    Keys are configured via API_KEYS environment variable (comma-separated).
    Example: API_KEYS=key1,key2,key3
    """
    valid_keys_str = os.getenv("API_KEYS", "")
    if not valid_keys_str:
        # No keys configured - security risk! Log warning but allow in dev
        import logging
        logging.warning("⚠️  API_KEYS not configured - API authentication is DISABLED")
        return "dev-mode-no-auth"
    
    valid_keys = [k.strip() for k in valid_keys_str.split(",") if k.strip()]
    
    provided_key = x_api_key or api_key_query
    
    if not provided_key or provided_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide valid X-Api-Key header or ?api_key= query param."
        )
    
    return provided_key

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
def list_jobs(
    db: SessionLocal = Depends(get_db)
):
    """
    Returns a history of all user story jobs.
    Public endpoint - no authentication required.
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
    Public endpoint - no authentication required.
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
async def stream_job_logs(
    job_id: str
):
    """
    SSE endpoint to stream live logs from Redis Pub/Sub.
    Public endpoint - no authentication required.
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
            r.close()

    return StreamingResponse(redis_event_generator(), media_type="text/event-stream")


# ── Planning Agent Endpoints ────────────────────────────────────────────────

class PlanningBatchRequest(BaseModel):
    repo_url: HttpUrl
    inputs: List[Any]  # Can be strings or dicts
    planning_mode: Optional[str] = "sequential"  # "sequential" or "parallel"
    auto_execute: Optional[bool] = True

class PlanningChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class PlanningChatResponse(BaseModel):
    session_id: str
    batch_id: Optional[str]
    response: str
    state: str
    story: Optional[Dict[str, Any]] = None
    execution_job_id: Optional[str] = None
    next_session: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any]
    celery_task_id: Optional[str] = None  # Task ID for polling
    message: Optional[str] = None  # Human-readable status message

class PlanningBatchResponse(BaseModel):
    batch_id: str
    summary: Dict[str, int]
    execution_jobs: List[str]
    planning_sessions: List[Dict[str, Any]]
    celery_task_id: Optional[str] = None  # Task ID for polling
    status: Optional[str] = None  # PENDING, PROCESSING, COMPLETE, FAILED
    message: Optional[str] = None  # Human-readable status message


@app.post("/api/v1/planning/batch", response_model=PlanningBatchResponse)
def create_planning_batch(
    req: PlanningBatchRequest,
    db: SessionLocal = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Submit a batch of user story requests for planning (async via Celery).
    
    Returns immediately with batch_id. Planning happens in background.
    - Complete stories are queued to execution immediately
    - Incomplete stories create planning sessions for clarification
    - Sequential mode (default): activate sessions one at a time
    - Parallel mode: activate all sessions simultaneously
    
    Poll `/api/v1/planning/batches/{batch_id}` for status updates.
    
    **Authentication Required:** Provide X-Api-Key header.
    """
    from api.database import PlanningBatch
    from worker.tasks import process_planning_batch
    import uuid
    
    # Create batch record immediately
    batch = PlanningBatch(
        id=f"batch-{uuid.uuid4().hex[:12]}",
        repo_url=str(req.repo_url),
        planning_mode=req.planning_mode,
        auto_execute=1 if req.auto_execute else 0,
        status="PENDING"
    )
    db.add(batch)
    db.commit()
    
    # Submit to Celery
    task = process_planning_batch.delay(
        batch_id=batch.id,
        repo_url=str(req.repo_url),
        inputs=req.inputs,
        planning_mode=req.planning_mode,
        auto_execute=req.auto_execute
    )
    
    # Update with Celery task ID
    batch.celery_task_id = task.id
    db.commit()
    
    return {
        "batch_id": batch.id,
        "summary": {
            "total": len(req.inputs),
            "needs_planning": len(req.inputs),  # Will be determined by worker
            "already_queued": 0  # Will be determined by worker
        },
        "execution_jobs": [],
        "planning_sessions": [],
        "celery_task_id": task.id,
        "status": "PENDING",
        "message": f"Batch submitted for processing. Poll /api/v1/planning/batches/{batch.id} for status."
    }


@app.post("/api/v1/planning/chat", response_model=PlanningChatResponse)
def planning_chat(
    req: PlanningChatRequest,
    db: SessionLocal = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Chat with a planning session to clarify requirements (async via Celery).
    
    - Omit session_id to start a new standalone session
    - Include session_id to continue an existing conversation
    - Submits to Celery and returns task_id for polling
    
    **For synchronous chat, use /api/v1/planning/chat/sync endpoint instead.**
    
    **Authentication Required:** Provide X-Api-Key header.
    """
    from api.database import PlanningSession
    from worker.tasks import process_planning_message
    from agents.planning_service import PlanningService
    import uuid
    
    # New standalone session (not part of a batch)
    if not req.session_id:
        service = PlanningService(None)  # No LLM client needed for session creation
        session = service._create_planning_session(
            db=db,
            batch_id=None,
            user_input=req.message,
            state="active"
        )
        db.commit()
        
        # Submit initial question generation to Celery
        task = process_planning_message.delay(
            session_id=session.id,
            message=req.message
        )
        
        return {
            "session_id": session.id,
            "batch_id": None,
            "response": "Processing your request...",
            "state": "active",
            "metadata": {
                "iteration": 0,
                "questions_asked": 0,
                "max_iterations": 10
            },
            "celery_task_id": task.id,
            "message": f"Session created. Poll /api/v1/planning/sessions/{session.id} for the first question."
        }
    else:
        # Continue existing session - submit to Celery
        task = process_planning_message.delay(
            session_id=req.session_id,
            message=req.message
        )
        
        session = db.query(PlanningSession).filter(PlanningSession.id == req.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session.id,
            "batch_id": session.batch_id,
            "response": "Processing your message...",
            "state": session.state,
            "metadata": {
                "iteration": session.iteration,
                "questions_asked": session.questions_asked,
                "max_iterations": session.max_iterations
            },
            "celery_task_id": task.id,
            "message": f"Message submitted. Poll /api/v1/planning/sessions/{session.id} for response."
        }


@app.get("/api/v1/planning/batches/{batch_id}")
def get_planning_batch(
    batch_id: str,
    db: SessionLocal = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Get status of a planning batch and all its sessions.
    
    **Authentication Required:** Provide X-Api-Key header.
    """
    from agents.planning_service import PlanningService
    from celery.result import AsyncResult
    
    service = PlanningService(None)  # No LLM client needed for queries
    batch = service.get_batch(db, batch_id)
    
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Get Celery task status if available
    celery_status = None
    if batch.celery_task_id:
        task_result = AsyncResult(batch.celery_task_id)
        celery_status = {
            "task_id": batch.celery_task_id,
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None
        }
    
    sessions_data = []
    for session in batch.sessions:
        session_data = {
            "session_id": session.id,
            "state": session.state,
            "user_input": session.user_input,
            "questions_asked": session.questions_asked,
            "execution_job_id": session.execution_job_id
        }
        
        if session.state == "complete" and session.story_result:
            session_data["story"] = session.story_result
        
        sessions_data.append(session_data)
    
    completed = len([s for s in batch.sessions if s.state == "complete"])
    active = len([s for s in batch.sessions if s.state == "active"])
    pending = len([s for s in batch.sessions if s.state == "pending"])
    
    return {
        "batch_id": batch.id,
        "repo_url": batch.repo_url,
        "planning_mode": batch.planning_mode,
        "status": batch.status,
        "celery_task": celery_status,
        "error_message": batch.error_message,
        "sessions": sessions_data,
        "progress": {
            "completed": completed,
            "active": active,
            "pending": pending,
            "total": len(batch.sessions)
        },
        "created_at": str(batch.created_at),
        "updated_at": str(batch.updated_at)
    }


@app.get("/api/v1/planning/sessions/{session_id}")
def get_planning_session(
    session_id: str,
    db: SessionLocal = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Get detailed status of a planning session including conversation history.
    
    **Authentication Required:** Provide X-Api-Key header.
    """
    from agents.planning_service import PlanningService
    
    service = PlanningService(Config.get_llm_client())
    session = service.get_session(db, session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session.id,
        "batch_id": session.batch_id,
        "state": session.state,
        "user_input": session.user_input,
        "current_question": session.current_question,
        "conversation_history": session.conversation_history or [],
        "story_result": session.story_result,
        "execution_job_id": session.execution_job_id,
        "metadata": {
            "iteration": session.iteration,
            "questions_asked": session.questions_asked,
            "max_iterations": session.max_iterations,
            "created_at": str(session.created_at),
            "updated_at": str(session.updated_at),
            "completed_at": str(session.completed_at) if session.completed_at else None
        },
        "error_message": session.error_message
    }


@app.get("/health")
def health_check():
    """Simple healthcheck for ECS Target Groups"""
    return {
        "status": "healthy",
        "version": Config.get_app_version()
    }
