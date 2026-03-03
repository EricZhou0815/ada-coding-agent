import sys
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Callable, Any

class LogHandler:
    """Base class for log handlers."""
    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        raise NotImplementedError

class TerminalHandler(LogHandler):
    """ANSI terminal output handler."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"

    COLORS = {
        "info": CYAN,
        "thought": MAGENTA,
        "tool": YELLOW,
        "success": GREEN,
        "error": RED,
        "warning": YELLOW
    }

    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        color = self.COLORS.get(level, self.CYAN)
        
        if level == "thought":
            print(f"{self.DIM}╭─ {prefix}'s Thought ───────────────{self.RESET}")
            for line in message.strip().split('\n'):
                print(f"{self.DIM}│ {line}{self.RESET}")
            print(f"{self.DIM}╰────────────────────────────────{self.RESET}")
        elif level == "tool":
            args = metadata.get("args") if metadata else None
            print(f"{self.BOLD}{color}[{prefix}]{self.RESET} ⚙ Calling {message}({args})")
        elif level == "tool_result":
            success = metadata.get("success") if metadata else False
            output_len = metadata.get("output_len") if metadata else 0
            icon = "✓" if success else "✗"
            status = f"successfully. (Returned {output_len} bytes)" if success else "failed."
            print(f"{self.BOLD}{self.YELLOW}[{prefix}]{self.RESET} {icon} Tool executed {status}")
        elif level == "success":
            print(f"\n{self.BOLD}{self.GREEN}✅ {message}{self.RESET}")
        else:
            icon = "✗" if level == "error" else "⚠" if level == "warning" else ""
            print(f"{self.BOLD}{color}[{prefix}]{self.RESET} {icon} {message}")

class DatabaseHandler(LogHandler):
    """Persists structured logs to the database."""
    def __init__(self, job_id: str):
        self.job_id = job_id

    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        from api.database import SessionLocal, StoryJob
        db = SessionLocal()
        job = db.query(StoryJob).filter(StoryJob.id == self.job_id).first()
        if job:
            try:
                logs = json.loads(job.logs) if job.logs else []
                logs.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": level,
                    "prefix": prefix,
                    "message": message,
                    "metadata": metadata or {}
                })
                job.logs = json.dumps(logs)
                db.commit()
            except Exception as e:
                # Log to stderr so failures aren't completely silent
                import sys
                print(f"[Logger] Failed to persist log to database: {e}", file=sys.stderr)
        db.close()

class RedisHandler(LogHandler):
    """Streams logs to Redis Pub/Sub for UI consumption."""
    def __init__(self, job_id: str):
        self.job_id = job_id
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.r = redis.from_url(redis_url)

    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "prefix": prefix,
            "message": message,
            "metadata": metadata or {}
        }
        try:
            self.r.publish(f"logs:{self.job_id}", json.dumps(payload))
            # Also persist once to DB via separate logic if needed, 
            # but for now, we assume the worker task handles DB persistence.
        except:
            pass

class AdaLogger:
    """
    Centralized logger that distributes logs to registered handlers.
    Used by agents, orchestrators, and tools to provide visibility to UI and Terminal.
    """
    def __init__(self):
        self.handlers: List[LogHandler] = [TerminalHandler()]
        self.job_id: Optional[str] = None

    def set_job_id(self, job_id: str):
        """Attaches the logger to a specific job, enabling multi-destination streaming."""
        self.job_id = job_id
        # Clear existing job-specific handlers
        self.handlers = [h for h in self.handlers if not isinstance(h, (RedisHandler, DatabaseHandler))]
        self.handlers.append(RedisHandler(job_id))
        self.handlers.append(DatabaseHandler(job_id))

    def _log(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        for handler in self.handlers:
            handler.emit(level, prefix, message, metadata)

    def info(self, prefix: str, msg: str):
        self._log("info", prefix, msg)

    def step(self, agent_name: str, msg: str):
        self._log("info", agent_name, f"🚀 {msg}")

    def thought(self, agent_name: str, content: str):
        self._log("thought", agent_name, content)

    def tool(self, agent_name: str, tool_name: str, args: dict):
        safe_args = json.dumps(args, default=str)
        if len(safe_args) > 100:
            safe_args = safe_args[:97] + "..."
        self._log("tool", agent_name, tool_name, {"args": safe_args})

    def tool_result(self, agent_name: str, success: bool, result: Any = None, output_len_bytes: int = 0):
        # Truncate result for UI visibility
        safe_result = str(result)
        if len(safe_result) > 500:
            safe_result = safe_result[:497] + "..."
            
        self._log("tool_result", agent_name, "", {
            "success": success, 
            "output_len": output_len_bytes,
            "result": safe_result if result is not None else None
        })

    def success(self, msg: str):
        self._log("success", "System", msg)

    def error(self, prefix: str, msg: str):
        self._log("error", prefix, msg)

    def warning(self, prefix: str, msg: str):
        self._log("warning", prefix, msg)

logger = AdaLogger()
