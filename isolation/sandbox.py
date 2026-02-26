"""
Sandboxed isolation backend for Ada.
Provides file-system and execution isolation without Docker.
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Dict, List
from isolation.backend import IsolationBackend


class SandboxBackend(IsolationBackend):
    """
    Sandboxed execution backend.
    Creates an isolated workspace and restricts file access.
    """
    
    def __init__(self, workspace_root: str = None):
        """
        Initialize the sandbox backend.
        
        Args:
            workspace_root: Root directory for sandbox workspaces
        """
        self.workspace_root = workspace_root or os.path.join(os.getcwd(), ".ada_sandbox")
        self.current_workspace = None
        self.original_cwd = None
        
    def setup(self, task: Dict, repo_path: str) -> None:
        """
        Set up the sandboxed workspace.
        Creates a temporary isolated workspace and copies the repo.
        """
        task_id = task.get('task_id', 'unknown')
        self.current_workspace = os.path.join(self.workspace_root, f"task_{task_id}")
        
        # Create workspace directory
        os.makedirs(self.current_workspace, exist_ok=True)
        
        # Create isolated repo directory
        isolated_repo = os.path.join(self.current_workspace, "repo")
        if os.path.exists(isolated_repo):
            shutil.rmtree(isolated_repo)
        
        # Copy repo snapshot to isolated workspace
        shutil.copytree(repo_path, isolated_repo)
        
        print(f"[Sandbox] Workspace created at: {self.current_workspace}")
        print(f"[Sandbox] Isolated repo at: {isolated_repo}")
    
    def execute(self, task: Dict, repo_path: str, completed_tasks: List[str]) -> bool:
        """
        Execute the task in the sandboxed environment.
        """
        if not self.current_workspace:
            raise RuntimeError("Sandbox not set up. Call setup() first.")
        
        isolated_repo = os.path.join(self.current_workspace, "repo")
        
        # Save current working directory
        self.original_cwd = os.getcwd()
        
        try:
            # Import Ada components
            from agents.coding_agent import AdaCodingAgent
            from agents.validation_agent import AdaValidationAgent
            from agents.llm_client import OpenAIClient
            from agents.mock_llm_client import MockLLMClient
            from tools.tools import AdaTools
            from orchestrator.task_executor import AtomicTaskExecutor
            
            # Initialize components with restricted tools
            tools = SandboxedTools(isolated_repo)
            
            # Use mock or real LLM based on API key availability
            if os.getenv("OPENAI_API_KEY"):
                llm_client = OpenAIClient()
                print("[Sandbox] Using OpenAI LLM")
            else:
                llm_client = MockLLMClient()
                print("[Sandbox] Using Mock LLM (no API key)")
            
            coding_agent = AdaCodingAgent(llm_client, tools)
            validation_agent = AdaValidationAgent()
            executor = AtomicTaskExecutor(
                coding_agent,
                validation_agent,
                isolated_repo,
                max_iterations=25
            )
            
            # Execute task
            print(f"[Sandbox] Executing task: {task['title']}")
            executor.execute_task(task, completed_tasks)
            
            # Copy results back to original repo
            self._copy_results_back(isolated_repo, repo_path)
            
            return True
            
        except Exception as e:
            print(f"[Sandbox] Execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Restore working directory
            if self.original_cwd:
                os.chdir(self.original_cwd)
    
    def _copy_results_back(self, isolated_repo: str, original_repo: str):
        """
        Copy modified files from isolated workspace back to original repo.
        """
        print(f"[Sandbox] Copying results back to {original_repo}")
        
        # Copy all files back (in production, you might want to be more selective)
        for item in os.listdir(isolated_repo):
            src = os.path.join(isolated_repo, item)
            dst = os.path.join(original_repo, item)
            
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        
        print("[Sandbox] Results copied successfully")
    
    def cleanup(self) -> None:
        """
        Clean up the sandboxed workspace.
        """
        if self.current_workspace and os.path.exists(self.current_workspace):
            print(f"[Sandbox] Cleaning up workspace: {self.current_workspace}")
            shutil.rmtree(self.current_workspace)
            self.current_workspace = None
    
    def get_name(self) -> str:
        """Get backend name."""
        return "Sandbox"


class SandboxedTools:
    """
    Restricted tools that only operate within the sandbox.
    """
    
    def __init__(self, allowed_path: str):
        """
        Initialize sandboxed tools.
        
        Args:
            allowed_path: The only directory where file operations are allowed
        """
        self.allowed_path = os.path.abspath(allowed_path)
    
    def _validate_path(self, path: str) -> str:
        """
        Validate that a path is within the allowed directory.
        
        Args:
            path: Path to validate
            
        Returns:
            Absolute path if valid
            
        Raises:
            SecurityError: If path is outside allowed directory
        """
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(self.allowed_path):
            raise SecurityError(f"Access denied: {path} is outside sandbox")
        return abs_path
    
    def read_file(self, path: str) -> str:
        """Read a file (restricted to sandbox)."""
        safe_path = self._validate_path(path)
        with open(safe_path, "r") as f:
            return f.read()
    
    def write_file(self, path: str, content: str):
        """Write to a file (restricted to sandbox)."""
        safe_path = self._validate_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(content)
    
    def delete_file(self, path: str):
        """Delete a file (restricted to sandbox)."""
        safe_path = self._validate_path(path)
        os.remove(safe_path)
    
    def list_files(self, directory: str) -> List[str]:
        """List files in a directory (restricted to sandbox)."""
        safe_dir = self._validate_path(directory)
        return os.listdir(safe_dir)
    
    def run_command(self, command: str) -> Dict:
        """
        Execute a shell command (restricted and monitored).
        
        Note: In production, you'd want to further restrict allowed commands.
        """
        import subprocess
        
        # Blacklist dangerous commands
        dangerous = ['rm -rf', 'del /f', 'format', 'mkfs', 'dd if=']
        if any(danger in command.lower() for danger in dangerous):
            return {
                "stdout": "",
                "stderr": "Command blocked for security reasons",
                "exit_code": 1
            }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.allowed_path,
                timeout=30  # 30 second timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out (30s limit)",
                "exit_code": 1
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1
            }
    
    def apply_patch(self, patch_text: str):
        """Apply a git patch (placeholder)."""
        # TODO: Implement safe patch application
        pass


class SecurityError(Exception):
    """Raised when a security violation is attempted."""
    pass
