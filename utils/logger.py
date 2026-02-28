import sys
import json

class TerminalLogger:
    """
    Zero-dependency ANSI terminal logger for Ada agents and orchestrator.
    Improves observability natively without 3rd party packages.
    """
    
    # ANSI escape codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"

    @classmethod
    def info(cls, prefix: str, msg: str):
        """Standard pipeline info execution."""
        print(f"{cls.BOLD}{cls.CYAN}[{prefix}]{cls.RESET} {msg}")

    @classmethod
    def step(cls, agent_name: str, msg: str):
        """When an agent begins execution."""
        print(f"\n{cls.BOLD}{cls.MAGENTA}[{agent_name}]{cls.RESET} {msg}")

    @classmethod
    def thought(cls, agent_name: str, content: str):
        """Renders an agent's internal monologue in a boxed-like format."""
        if not content.strip():
            return
            
        print(f"{cls.DIM}╭─ {agent_name}'s Thought ───────────────{cls.RESET}")
        for line in content.strip().split('\n'):
            print(f"{cls.DIM}│ {line}{cls.RESET}")
        print(f"{cls.DIM}╰────────────────────────────────{cls.RESET}")

    @classmethod
    def tool(cls, agent_name: str, tool_name: str, args: dict):
        """Formats tool execution cleanly."""
        safe_args = json.dumps(args, default=str)
        if len(safe_args) > 100:
            safe_args = safe_args[:97] + "..."
            
        print(f"{cls.BOLD}{cls.YELLOW}[{agent_name}]{cls.RESET} ⚙ Calling {tool_name}({safe_args})")

    @classmethod
    def tool_result(cls, agent_name: str, success: bool, output_len_bytes: int = 0):
        if success:
            print(f"{cls.BOLD}{cls.YELLOW}[{agent_name}]{cls.RESET} ✓ Tool executed successfully. (Returned {output_len_bytes} bytes)")
        else:
            print(f"{cls.BOLD}{cls.YELLOW}[{agent_name}]{cls.RESET} ✗ Tool execution failed.")

    @classmethod
    def success(cls, msg: str):
        print(f"\n{cls.BOLD}{cls.GREEN}✅ {msg}{cls.RESET}")

    @classmethod
    def error(cls, prefix: str, msg: str):
        print(f"{cls.BOLD}{cls.RED}[{prefix}] ✗ {msg}{cls.RESET}")

    @classmethod
    def warning(cls, prefix: str, msg: str):
        print(f"{cls.BOLD}{cls.YELLOW}[{prefix}] ⚠ {msg}{cls.RESET}")

logger = TerminalLogger()
