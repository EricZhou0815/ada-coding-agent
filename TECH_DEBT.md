# Technical Debt Registry

This document tracks known technical debt and areas for improvement in the Ada codebase.
Items are prioritized based on risk and impact.

---

## 🟡 P1: Address Before Public Beta

### 1. Shell Command Injection Risk
**Location:** `tools/tools.py` - `run_command()` method  
**Risk:** HIGH - LLM can hallucinate malicious shell commands  
**Current State:** `shell=True` with no command filtering

**Mitigation (Current):**
- Only deploy for internal/trusted users
- Don't expose to public internet without auth

**Recommended Fix:**
- Implement command whitelist (e.g., only `npm`, `pytest`, `make`)
- Use `shlex.split()` and avoid `shell=True`
- Add audit logging for all executed commands

```python
# Example fix
ALLOWED_COMMANDS = {"npm", "pytest", "python", "make", "cargo"}

def run_command(self, command: str) -> Dict:
    parts = shlex.split(command)
    if parts[0] not in ALLOWED_COMMANDS:
        return {"error": f"Command '{parts[0]}' not in allowlist"}
    result = subprocess.run(parts, capture_output=True, text=True)  # No shell=True
    ...
```

---

### 2. Silent Exception Swallowing
**Location:** `utils/logger.py` lines 66-68  
**Risk:** MEDIUM - Database write failures go unnoticed, logs silently lost

**Current State:**
```python
except:
    pass  # Silent failure
```

**Recommended Fix:**
```python
except Exception as e:
    # At minimum, log to stderr
    import sys
    print(f"[Logger] Failed to persist log: {e}", file=sys.stderr)
```

---

### 3. No Webhook Idempotency
**Location:** `api/webhooks/vcs.py`, `worker/tasks.py`  
**Risk:** MEDIUM - Webhook retries could trigger duplicate CI fixes or PR updates

**Mitigation (Current):**
- GitHub webhook retries are infrequent in practice

**Recommended Fix:**
- Store `X-GitHub-Delivery` header ID in Redis
- Check for duplicates before dispatching task
- TTL of ~1 hour for deduplication keys

```python
delivery_id = request.headers.get("X-GitHub-Delivery")
if redis_client.exists(f"webhook:{delivery_id}"):
    return {"status": "ignored", "reason": "duplicate"}
redis_client.setex(f"webhook:{delivery_id}", 3600, "1")
```

---

## 🟢 P2: Address When Scaling

### 4. Database Connection Per Log Line
**Location:** `utils/logger.py` - `DatabaseHandler.emit()`  
**Risk:** LOW at MVP scale → HIGH at ~50+ concurrent jobs

**Current State:** Opens/closes DB session for every log entry

**Recommended Fix:**
- Use connection pooling properly
- Batch log writes (buffer N entries, flush periodically)
- Move to async writes with background worker

---

### 5. Logs Stored as JSON in Text Column
**Location:** `api/database.py` - `StoryJob.logs`  
**Risk:** LOW at MVP → Query performance degrades at scale

**Current State:** 
```python
logs = Column(Text, default="[]")  # JSON array as string
```

**Recommended Fix:**
- Create separate `job_logs` table with proper indices
- Or use PostgreSQL JSONB column type
- Add pagination for log retrieval API

---

### 6. Token Injected in Git Clone URL
**Location:** `tools/git_manager.py` lines 55-57  
**Risk:** LOW - Could leak to logs/stack traces despite partial scrubbing

**Recommended Fix:**
- Use `git credential.helper` instead
- Or use SSH keys for auth
- Ensure all error handlers scrub tokens

---

### 7. SQLite in Dev with No Migration Path
**Location:** `api/database.py` - `init_db()` on import  
**Risk:** LOW - Schema changes require manual migration

**Recommended Fix:**
- Integrate Alembic for schema migrations
- Add migration scripts to CI/CD

---

## 🔵 P3: Nice to Have (Post-MVP)

### 8. No Distributed Tracing
**Impact:** Can't correlate webhook → celery task → agent loop across services

**Recommendation:** Add OpenTelemetry tracing with trace ID propagation

---

### 9. No Metrics/Alerting
**Impact:** No visibility into tool call latency, failure rates, LLM costs

**Recommendation:** 
- Add Prometheus metrics endpoint
- Track: `tool_calls_total`, `llm_latency_seconds`, `key_rotation_count`

---

### 10. Lost Redis Pub/Sub Messages
**Impact:** If no subscriber active, streaming logs vanish

**Recommendation:** 
- Switch to Redis Streams with consumer groups
- Or persist to DB first, then publish

---

### 11. Branch Name Collision
**Location:** `orchestrator/sdlc_orchestrator.py`  
**Impact:** If same story submitted twice → both try to create `ada/STORY-1-*`

**Recommendation:**
- Add job-level mutex using Redis SETNX
- Or append timestamp/UUID to branch names

---

### 12. Checkpoint File Corruption
**Location:** `agents/coding_agent.py` - `_save_checkpoint()`  
**Impact:** Crash mid-write → invalid JSON → unrecoverable state

**Recommendation:**
```python
# Atomic write pattern
temp_path = path + ".tmp"
with open(temp_path, "w") as f:
    json.dump(state, f)
os.replace(temp_path, path)  # Atomic on POSIX/Windows
```

---

### 13. No Memory Limits on LLM Context
**Location:** `agents/llm_client.py` - `conversation_history`  
**Impact:** 80 tool calls × large file reads = memory/context explosion

**Recommendation:**
- Add `max_context_tokens` config
- Implement sliding window or summarization for long conversations

---

### 14. Disk Exhaustion in Workers
**Location:** `/tmp/ada_runs/` accumulates on failed cleanup  
**Impact:** Celery workers eventually OOM or disk-fill

**Recommendation:**
- Add cron job to clean old workspaces
- Set `ADA_TMP_DIR` to a volume with quotas
- Add monitoring alert for disk usage

---

## ✅ Resolved

| Issue | Resolution | Date |
|-------|------------|------|
| Webhook signature verification | Implemented HMAC-SHA256 validation | 2026-03-03 |
| PR comment author validation | Added collaborator check | 2026-03-03 |
| Single API key point of failure | Implemented key pool rotation | 2026-03-03 |

---

## Contributing

When fixing technical debt:
1. Update the status in this file
2. Add tests for the fix
3. Move item to "Resolved" table with date
