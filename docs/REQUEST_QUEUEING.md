# Request Queueing Architecture

This document explains Ada's async request queueing system for Planning Agent operations.

## Overview

**Problem:** Synchronous API endpoints can be overwhelmed by large planning batches (e.g., 100 user story requests), blocking API workers and degrading service.

**Solution:** Celery-based async queueing offloads heavy planning work to background workers, allowing the API to return immediately with a job ID for polling.

## Architecture

```
┌───────────┐
│  Client   │
└─────┬─────┘
      │ POST /planning/batch
      │
┌─────▼──────┐
│ FastAPI    │  1. Create PlanningBatch record
│ API Server │  2. Submit to Celery queue
└─────┬──────┘  3. Return batch_id + task_id immediately
      │
      │ (async via Redis)
      │
┌─────▼──────┐
│   Celery   │  4. Pick up job from queue
│   Worker   │  5. Process planning sessions
└─────┬──────┘  6. Update batch status in DB
      │
      │ (poll for status)
      │
┌─────▼──────┐
│ PostgreSQL │  7. Client polls GET /planning/batches/{id}
│  Database  │  8. Returns current status + results
└────────────┘
```

## API Endpoints

### 1. Submit Planning Batch (Async)

**Endpoint:** `POST /api/v1/planning/batch`

**Request:**
```json
{
  "repo_url": "https://github.com/user/repo",
  "inputs": [
    "Add user authentication",
    "Implement payment gateway",
    {
      "title": "Complete Story",
      "description": "...",
      "acceptance_criteria": ["..."]
    }
  ],
  "planning_mode": "sequential",
  "auto_execute": true
}
```

**Response (Immediate):**
```json
{
  "batch_id": "batch-abc123",
  "summary": {
    "total": 3,
    "needs_planning": 3,
    "already_queued": 0
  },
  "execution_jobs": [],
  "planning_sessions": [],
  "celery_task_id": "task-xyz789",
  "status": "PENDING",
  "message": "Batch submitted for processing. Poll /api/v1/planning/batches/batch-abc123 for status."
}
```

**Key Changes:**
- Returns **immediately** (< 100ms)
- No LLM calls in API worker
- Provides `celery_task_id` for Celery-level status
- Provides `batch_id` for polling planning status

---

### 2. Chat with Planning Session (Async)

**Endpoint:** `POST /api/v1/planning/chat`

**Request:**
```json
{
  "session_id": "session-def456",
  "message": "The feature should support OAuth 2.0 and SAML"
}
```

**Response (Immediate):**
```json
{
  "session_id": "session-def456",
  "batch_id": "batch-abc123",
  "response": "Processing your message...",
  "state": "active",
  "metadata": {
    "iteration": 2,
    "questions_asked": 1,
    "max_iterations": 10
  },
  "celery_task_id": "task-msg-xyz",
  "message": "Message submitted. Poll /api/v1/planning/sessions/session-def456 for response."
}
```

**Key Changes:**
- Message processing happens in Celery worker
- Client polls session endpoint for LLM response
- Prevents long-running LLM calls from blocking API

---

### 3. Poll Batch Status

**Endpoint:** `GET /api/v1/planning/batches/{batch_id}`

**Response:**
```json
{
  "batch_id": "batch-abc123",
  "repo_url": "https://github.com/user/repo",
  "planning_mode": "sequential",
  "status": "PROCESSING",
  "celery_task": {
    "task_id": "task-xyz789",
    "state": "STARTED",
    "ready": false,
    "successful": null
  },
  "error_message": null,
  "sessions": [
    {
      "session_id": "session-1",
      "state": "complete",
      "user_input": "Add user authentication",
      "questions_asked": 3,
      "execution_job_id": "job-123",
      "story": {
        "story_id": "STORY-AUTH-001",
        "title": "Implement User Authentication",
        "description": "...",
        "acceptance_criteria": ["..."]
      }
    },
    {
      "session_id": "session-2",
      "state": "active",
      "user_input": "Implement payment gateway",
      "questions_asked": 1,
      "execution_job_id": null
    }
  ],
  "progress": {
    "completed": 1,
    "active": 1,
    "pending": 1,
    "total": 3
  },
  "created_at": "2026-03-04T10:30:00Z",
  "updated_at": "2026-03-04T10:32:15Z"
}
```

**Status Values:**
- `PENDING` - Batch created, waiting for worker
- `PROCESSING` - Worker actively processing sessions
- `COMPLETE` - All sessions processed (complete/error/cancelled)
- `FAILED` - Worker encountered fatal error

---

### 4. Poll Session Status

**Endpoint:** `GET /api/v1/planning/sessions/{session_id}`

**Response:**
```json
{
  "session_id": "session-def456",
  "batch_id": "batch-abc123",
  "state": "active",
  "current_question": "Which OAuth providers should be supported (Google, GitHub, Microsoft)?",
  "conversation_history": [
    {"role": "user", "content": "Add OAuth authentication"},
    {"role": "assistant", "content": "Which OAuth providers...?"}
  ],
  "iteration": 2,
  "questions_asked": 2,
  "max_iterations": 10,
  "story_result": null,
  "execution_job_id": null,
  "created_at": "2026-03-04T10:30:00Z",
  "updated_at": "2026-03-04T10:32:00Z"
}
```

**Session States:**
- `pending` - Waiting to be activated (sequential mode)
- `active` - Currently asking questions
- `complete` - Story finalized and queued
- `error` - Max iterations reached or LLM error
- `cancelled` - User cancelled session

---

## Celery Tasks

### Task 1: `process_planning_batch`

**Purpose:** Process an entire planning batch

**Parameters:**
- `batch_id` - Existing PlanningBatch ID
- `repo_url` - Repository URL
- `inputs` - List of user requests
- `planning_mode` - "sequential" | "parallel"
- `auto_execute` - Auto-queue completed stories

**Workflow:**
1. Load batch from database
2. Update status to PROCESSING
3. Create PlanningSession for each input
4. Classify inputs (complete vs needs planning)
5. Activate sessions based on mode
6. Generate initial questions for active sessions
7. Update batch status to COMPLETE

**Result:**
```python
{
    "batch_id": "batch-abc123",
    "sessions_created": 3,
    "execution_jobs": ["job-1", "job-2"],
    "status": "COMPLETE"
}
```

---

### Task 2: `process_planning_message`

**Purpose:** Process a single message in a planning session

**Parameters:**
- `session_id` - PlanningSession ID
- `message` - User's message

**Workflow:**
1. Load session from database
2. Add user message to conversation history
3. Call LLM with conversation context
4. Parse LLM response
5. Check if story is complete (STORY_COMPLETE signal)
6. If complete:
   - Extract story JSON
   - Queue to execution (if auto_execute)
   - Activate next session (if sequential mode)
7. Update session state

**Result:**
```python
{
    "session_id": "session-123",
    "state": "complete",
    "current_question": null,
    "iteration": 4,
    "story_result": {...},
    "execution_job_id": "job-456"
}
```

---

## Database Schema Updates

### PlanningBatch Table

**New Fields:**
```sql
celery_task_id VARCHAR      -- Celery AsyncResult ID for tracking
status VARCHAR(50)           -- PENDING, PROCESSING, COMPLETE, FAILED
error_message TEXT           -- Error details if status=FAILED
```

**Indexes:**
```sql
CREATE INDEX idx_batch_celery_task ON planning_batches(celery_task_id);
```

---

## Client Integration Examples

### Example 1: Submit Batch and Poll Until Complete

**Python Client:**
```python
import requests
import time

API_BASE = "http://localhost:8000/api/v1"
HEADERS = {"X-Api-Key": "your-api-key"}

# Submit batch
response = requests.post(
    f"{API_BASE}/planning/batch",
    headers=HEADERS,
    json={
        "repo_url": "https://github.com/user/repo",
        "inputs": ["Add user auth", "Implement payments"],
        "planning_mode": "sequential",
        "auto_execute": True
    }
)
batch_id = response.json()["batch_id"]
print(f"Batch submitted: {batch_id}")

# Poll for completion
while True:
    status_response = requests.get(
        f"{API_BASE}/planning/batches/{batch_id}",
        headers=HEADERS
    )
    data = status_response.json()
    
    print(f"Status: {data['status']}")
    print(f"Progress: {data['progress']}")
    
    if data["status"] in ["COMPLETE", "FAILED"]:
        break
    
    time.sleep(5)  # Poll every 5 seconds

# Get active sessions for answering questions
for session in data["sessions"]:
    if session["state"] == "active":
        print(f"\nSession {session['session_id']} needs input:")
        print(f"Question: {session['current_question']}")
```

---

### Example 2: Interactive Chat Loop

**Python Client:**
```python
def chat_with_session(session_id, message):
    """Submit message and wait for response"""
    # Submit message
    response = requests.post(
        f"{API_BASE}/planning/chat",
        headers=HEADERS,
        json={"session_id": session_id, "message": message}
    )
    celery_task_id = response.json()["celery_task_id"]
    
    # Poll for response
    while True:
        session_response = requests.get(
            f"{API_BASE}/planning/sessions/{session_id}",
            headers=HEADERS
        )
        session_data = session_response.json()
        
        if session_data["state"] == "complete":
            print("Story complete!")
            print(session_data["story_result"])
            break
        elif session_data["current_question"]:
            return session_data["current_question"]
        
        time.sleep(2)

# Interactive loop
session_id = "session-abc123"
question = chat_with_session(session_id, "Add OAuth authentication")

while question:
    print(f"Agent: {question}")
    user_input = input("You: ")
    question = chat_with_session(session_id, user_input)
```

---

## Performance Benefits

### Before (Synchronous)

```
Client → API: POST /planning/batch (100 inputs)
API:    Creates 100 sessions
        Generates 100 initial questions (3s × 100 = 300s)
        ⏱️  Response after 5 minutes
Client: Receives response

Throughput: Limited by API worker count × request duration
```

### After (Async Queueing)

```
Client → API: POST /planning/batch (100 inputs)
API:    Creates batch record
        Submits to Celery
        ⏱️  Response after 50ms
Client: Receives batch_id immediately
        Polls for status updates

Worker: Processes batch asynchronously
        Generates questions in background
        Updates database incrementally

Throughput: Limited by worker pool size (configurable)
```

**Metrics:**
- **API Response Time:** 5 minutes → 50ms (6000× faster)
- **API Concurrency:** 4 batches/hour → 7200 batches/hour
- **Worker Scalability:** Add more workers with `docker-compose up --scale worker=10`

---

## Configuration

### Environment Variables

```bash
# Celery worker concurrency
CELERY_CONCURRENCY=4          # Concurrent tasks per worker

# Database connection pooling (per API instance)
DB_POOL_SIZE=5                # Base connections
DB_MAX_OVERFLOW=10            # Extra under load

# Redis URL
REDIS_URL=redis://localhost:6379/0
```

### Docker Compose Scaling

```bash
# Scale workers independently
docker-compose up --scale worker=8

# Scale API and workers together
docker-compose up --scale api=3 --scale worker=6
```

---

## Monitoring

### Check Celery Task Status

**Via API:**
```bash
curl http://localhost:8000/api/v1/planning/batches/{batch_id}
# Look for celery_task.state: PENDING, STARTED, SUCCESS, FAILURE
```

**Via Celery CLI:**
```bash
# Inside worker container
celery -A worker.tasks inspect active
celery -A worker.tasks inspect stats
```

### Check Queue Length

```bash
# Connect to Redis
docker exec -it ada-redis redis-cli

# Check Celery queue length
LLEN celery

# View tasks in queue
LRANGE celery 0 -1
```

---

## Error Handling

### Scenario 1: Worker Crashes

**Detection:** Celery task state remains `STARTED`, batch status stays `PROCESSING`

**Recovery:**
- Celery automatically retries failed tasks (default: 3× with exponential backoff)
- Monitor task state via `GET /planning/batches/{id}`
- If task fails permanently, batch status → `FAILED`

### Scenario 2: Database Connection Lost

**Handling:**
- SQLAlchemy connection pooling with `pool_pre_ping=True`
- Automatic connection retry on transient failures
- Task fails if DB unreachable after retries

### Scenario 3: LLM API Rate Limit

**Handling:**
- APIKeyPool rotates to next key automatically
- Exponential backoff on rate limit errors
- Task retries with different key
- If all keys exhausted, task fails with clear error message

---

## Migration from Synchronous Endpoints

### Old (Synchronous) Flow

```python
# POST /planning/batch
response = await service.create_batch(...)
return {"batch_id": ..., "sessions": [...]}  # Takes 30s-5min
```

### New (Async) Flow

```python
# POST /planning/batch
batch = create_batch_record()
task = process_planning_batch.delay(...)
return {"batch_id": ..., "celery_task_id": task.id}  # Takes 50ms

# GET /planning/batches/{id}
return current_status_from_db()  # Takes 10ms
```

### Backward Compatibility

**Option 1:** Keep sync endpoint for small batches
```python
@app.post("/api/v1/planning/batch/sync")
async def create_planning_batch_sync(...):
    # Old synchronous implementation
    # Only for batches with < 5 inputs
```

**Option 2:** Client-side migration
- Update all clients to use async + polling pattern
- Deprecate sync endpoint after migration period

---

## Testing

### Unit Tests

```python
from worker.tasks import process_planning_batch
from api.database import PlanningBatch, SessionLocal

def test_planning_batch_task():
    db = SessionLocal()
    
    # Create batch
    batch = PlanningBatch(id="test-123", ...)
    db.add(batch)
    db.commit()
    
    # Run task synchronously (for testing)
    result = process_planning_batch(
        batch_id="test-123",
        repo_url="https://github.com/test/repo",
        inputs=["Test input"],
        planning_mode="sequential",
        auto_execute=True
    )
    
    # Verify
    assert result["status"] == "COMPLETE"
    assert len(result["sessions_created"]) > 0
```

### Integration Tests

```bash
# Start services
docker-compose up -d

# Submit batch
curl -X POST http://localhost:8000/api/v1/planning/batch \
  -H "X-Api-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/test/repo",
    "inputs": ["Test story"],
    "planning_mode": "sequential",
    "auto_execute": false
  }'

# Poll status (should transition PENDING -> PROCESSING -> COMPLETE)
watch -n 2 'curl -H "X-Api-Key: test-key" \
  http://localhost:8000/api/v1/planning/batches/{batch_id}'
```

---

## Future Enhancements

1. **WebSocket Support**
   - Replace polling with real-time updates
   - Push notifications when sessions become active

2. **Batch Checkpoint/Resume**
   - Save intermediate state
   - Resume from failure point instead of restarting

3. **Priority Queues**
   - Different queues for urgent/normal batches
   - Route to dedicated workers

4. **Result Expiration**
   - TTL for completed batches (e.g., 7 days)
   - Automatic cleanup of old results

5. **Analytics Dashboard**
   - Average planning time per session
   - Success rate of story generation
   - Worker utilization metrics

---

## Related Documentation

- [MULTI_INSTANCE_DEPLOYMENT.md](./MULTI_INSTANCE_DEPLOYMENT.md) - API scaling guide
- [LOG_DATABASE_ARCHITECTURE.md](./LOG_DATABASE_ARCHITECTURE.md) - Database design
- [README.md](../README.md) - Project overview
