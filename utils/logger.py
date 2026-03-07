import sys
import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Callable, Any

# Suppress noisy HTTP logs from OpenAI/Groq SDK
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Tool categories for intelligent filtering
READ_ONLY_TOOLS = {"list_files", "read_file", "search_codebase"}
WRITE_TOOLS = {"write_file", "edit_file", "delete_file", "apply_patch"}
EXECUTION_TOOLS = {"run_command"}

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
            # Format similar to tool calls but with purple/magenta color
            print(f"{self.BOLD}{self.MAGENTA}[{prefix}]{self.RESET} Thinking")
            for line in message.strip().split('\n'):
                print(f"  {self.DIM}{line}{self.RESET}")
        elif level == "tool":
            # Get formatted args from metadata for detailed display
            args_display = metadata.get("args_display") if metadata else None
            if args_display:
                print(f"{self.BOLD}{color}[{prefix}]{self.RESET} Calling {message}")
                for line in args_display.split('\n'):
                    print(f"  {self.DIM}{line}{self.RESET}")
            else:
                args = metadata.get("args") if metadata else None
                print(f"{self.BOLD}{color}[{prefix}]{self.RESET} Calling {message}({args})")
        elif level == "tool_result":
            success = metadata.get("success") if metadata else False
            result_display = metadata.get("result_display") if metadata else None
            
            if result_display:
                print(f"{self.BOLD}{self.YELLOW}[{prefix}]{self.RESET} {message}")
                # Show first few lines of result
                for line in result_display.split('\n')[:10]:  # Limit to 10 lines
                    print(f"  {self.DIM}{line}{self.RESET}")
            else:
                output_len = metadata.get("output_len") if metadata else 0
                status = f"successfully. (Returned {output_len} bytes)" if success else "failed."
                print(f"{self.BOLD}{self.YELLOW}[{prefix}]{self.RESET} {message} - Tool executed {status}")
        elif level == "success":
            print(f"\n{self.BOLD}{self.GREEN}SUCCESS: {message}{self.RESET}")
        else:
            prefix_text = "ERROR" if level == "error" else "WARNING" if level == "warning" else ""
            final_prefix = f"{prefix_text}: " if prefix_text else ""
            print(f"{self.BOLD}{color}[{prefix}]{self.RESET} {final_prefix}{message}")

class DatabaseHandler(LogHandler):
    """Persists structured logs to the database."""
    def __init__(self, job_id: str):
        self.job_id = job_id

    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        from api.database import SessionLocal, JobLog
        db = SessionLocal()
        try:
            # Simple INSERT into job_logs table - no JSON parsing overhead!
            log_entry = JobLog(
                job_id=self.job_id,
                timestamp=datetime.now(timezone.utc),
                level=level,
                prefix=prefix,
                message=message,
                meta=metadata or {}
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            # Log to stderr so failures aren't completely silent
            db.rollback()
            import sys
            print(f"[Logger] Failed to persist log to database: {e}", file=sys.stderr)
        finally:
            db.close()

class RedisHandler(LogHandler):
    """Streams logs to Redis Pub/Sub for UI consumption."""
    def __init__(self, job_id: str):
        self.job_id = job_id
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.r = redis.from_url(redis_url)

    def emit(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        # Metadata is already JSON-safe from _log() method
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "prefix": prefix,
            "message": message,
            "metadata": metadata or {}
        }
        try:
            # All data is already JSON-serializable
            self.r.publish(f"logs:{self.job_id}", json.dumps(payload))
        except Exception as e:
            # Log serialization errors for debugging
            import sys
            print(f"[RedisHandler] Failed to publish log: {e}", file=sys.stderr)
            pass

class AdaLogger:
    """
    Centralized logger that distributes logs to registered handlers.
    Used by agents, orchestrators, and tools to provide visibility to UI and Terminal.
    """
    def __init__(self):
        self.handlers: List[LogHandler] = [TerminalHandler()]
        self.job_id: Optional[str] = None
        self.current_phase: Optional[str] = None
        self.tool_count: int = 0
        self.max_tools: int = 80

    def set_job_id(self, job_id: str):
        """Attaches the logger to a specific job, enabling multi-destination streaming."""
        self.job_id = job_id
        # Clear existing job-specific handlers
        self.handlers = [h for h in self.handlers if not isinstance(h, (RedisHandler, DatabaseHandler))]
        self.handlers.append(RedisHandler(job_id))
        self.handlers.append(DatabaseHandler(job_id))
    
    def set_phase(self, phase: str):
        """Update current workflow phase for progress tracking."""
        self.current_phase = phase
    
    def set_progress(self, current: int, total: int):
        """Update tool call progress."""
        self.tool_count = current
        self.max_tools = total

    def _create_tool_summary(self, tool_name: str, args: dict) -> Optional[str]:
        """
        Create human-readable summary for tool calls.
        Returns None for read-only tools (they will be hidden).
        """
        # Hide read-only tools - only show actions that modify state
        if tool_name in READ_ONLY_TOOLS:
            return None
        
        # Write operations
        if tool_name == "write_file":
            path = args.get("path", "unknown")
            content = args.get("content", "")
            lines = len(content.split('\n'))
            return f"Creating {path} ({lines} lines)"
        
        elif tool_name == "edit_file":
            path = args.get("path", "unknown")
            old = args.get("target_content", "")
            new = args.get("replacement_content", "")
            old_lines = len(old.split('\n'))
            new_lines = len(new.split('\n'))
            change = new_lines - old_lines
            if change > 0:
                return f"Editing {path} (+{change} lines)"
            elif change < 0:
                return f"Editing {path} ({change} lines)"
            else:
                return f"Editing {path} (~{new_lines} lines changed)"
        
        elif tool_name == "delete_file":
            path = args.get("path", "unknown")
            return f"Deleting {path}"
        
        # Command execution
        elif tool_name == "run_command":
            cmd = args.get("command", "")
            # Truncate long commands
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            return f"Running: {cmd}"
        
        # Default for unknown tools
        return f"{tool_name}"

    def _log(self, level: str, prefix: str, message: str, metadata: Optional[dict] = None):
        # Enrich metadata with phase and progress for UI
        if metadata is None:
            metadata = {}
        
        if self.current_phase:
            metadata["phase"] = self.current_phase
        
        if self.tool_count > 0:
            metadata["progress"] = f"{self.tool_count}/{self.max_tools}"
        
        # CRITICAL: Ensure all metadata is JSON-serializable before sending to handlers
        # This is the central serialization point - converts ALL Python objects to JSON primitives
        # - Redis Pub/Sub requires JSON for transmission to UI
        # - Database storage works better with JSON-safe types
        # - Prevents React rendering errors from non-serializable objects
        # Uses json.dumps(default=str) to convert any remaining objects to strings
        json_safe_metadata = json.loads(json.dumps(metadata, default=str))
        
        for handler in self.handlers:
            handler.emit(level, prefix, message, json_safe_metadata)

    def info(self, prefix: str, msg: str):
        self._log("info", prefix, msg)

    def step(self, agent_name: str, msg: str):
        self._log("info", agent_name, f"STEP: {msg}")
    
    def phase(self, agent_name: str, phase: str, tool_count: int = None):
        """Log workflow phase transition."""
        self.set_phase(phase)
        if tool_count is not None:
            self.tool_count = tool_count
        
        progress = f" (Tool {self.tool_count}/{self.max_tools})" if self.tool_count > 0 else ""
        self._log("info", agent_name, f"PHASE: {phase.upper()}{progress}")

    def thought(self, agent_name: str, content: str):
        """Log agent's reasoning. Shows ALL thoughts for full visibility."""
        self._log("thought", agent_name, content)

    def tool(self, agent_name: str, tool_name: str, args: dict):
        """Log tool execution with full arguments for detailed visibility."""
        # Increment counter
        self.tool_count += 1
        
        # Format args for display in terminal (will be JSON-serialized by _log)
        args_str = json.dumps(args, indent=2, default=str) if args else "{}"
        
        # Send data - _log() will ensure JSON-safety before sending to handlers
        self._log("tool", agent_name, tool_name, {
            "tool_name": tool_name,
            "args": args,  # Original args (will be JSON-serialized by _log)
            "args_display": args_str  # Formatted version for terminal
        })

    def tool_result(self, agent_name: str, success: bool, result: Any = None, output_len_bytes: int = 0):
        """Log tool execution result with full output for detailed debugging."""
        # Create string representation for display
        result_str = str(result) if result else "No output"
        
        # Truncate only if extremely large (>2000 chars)
        if len(result_str) > 2000:
            result_display = result_str[:2000] + f"... (truncated, total: {len(result_str)} chars)"
        else:
            result_display = result_str
        
        status = "SUCCESS" if success else "FAILED"
        
        # Send data - _log() will ensure JSON-safety before sending to handlers
        self._log("tool_result", agent_name, status, {
            "success": success,
            "output_len": output_len_bytes,
            "result": result,  # Original result (will be JSON-serialized by _log)
            "result_display": result_display  # String version for terminal
        })

    def completion_summary(self, agent_name: str, changes: List[str] = None, tool_count: int = None):
        """Log task completion with summary of changes made."""
        summary = "TASK COMPLETE"
        
        if changes:
            summary += "\n\nChanges Made:"
            for change in changes[:10]:  # Limit to 10 items
                summary += f"\n  {change}"
        
        if tool_count:
            summary += f"\n\nCompleted in {tool_count} actions"
        
        self._log("success", agent_name, summary)

    def success(self, msg: str):
        self._log("success", "System", msg)

    def error(self, prefix: str, msg: str):
        self._log("error", prefix, msg)

    def warning(self, prefix: str, msg: str):
        self._log("warning", prefix, msg)

logger = AdaLogger()
