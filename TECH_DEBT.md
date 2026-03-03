# Technical Debt Registry

This document tracks known technical debt and areas for improvement in the Ada codebase.
Items are prioritized based on risk and impact.

---

## 🟡 P1: Address Before Public Beta

**All P1 items have been resolved!** See "Resolved" section below.

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
| Shell command injection risk | Implemented command allowlist with security checks | 2026-03-03 |
| Silent exception swallowing | Added stderr logging for database write failures | 2026-03-03 |
| Webhook idempotency | Implemented Redis deduplication with X-GitHub-Delivery | 2026-03-03 |
| Webhook signature verification | Implemented HMAC-SHA256 validation | 2026-03-03 |
| PR comment author validation | Added collaborator check | 2026-03-03 |
| Single API key point of failure | Implemented key pool rotation | 2026-03-03 |

---

## Contributing

When fixing technical debt:
1. Update the status in this file
2. Add tests for the fix
3. Move item to "Resolved" table with date
