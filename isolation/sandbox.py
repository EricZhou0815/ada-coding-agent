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
            from agents.coding_agent import CodingAgent
            from agents.validation_agent import ValidationAgent
            from config import Config
            from tools.tools import Tools
            from orchestrator.task_executor import PipelineOrchestrator
            from orchestrator.rule_provider import LocalFolderRuleProvider
            
            # Initialize components with restricted tools
            tools = SandboxedTools(isolated_repo)
            
            # Use configured LLM
            llm_client = Config.get_llm_client()
            print(f"[Sandbox] Using {Config.get_llm_provider().capitalize()} LLM")
            
            coding_agent = CodingAgent(llm_client, tools)
            validation_agent = ValidationAgent(llm_client, tools)
            agents_pipeline = [coding_agent, validation_agent]
            rule_providers = [LocalFolderRuleProvider()]
            executor = PipelineOrchestrator(
                agents_pipeline,
                rule_providers=rule_providers,
                max_retries=25
            )
            
            # Execute the task
            executor.execute_task(task, isolated_repo, completed_tasks)
            
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
        """
        Reads a file, restricting access to the sandbox directory.

        Args:
            path (str): The relative or absolute path to read.

        Returns:
            str: The target file's content.

        Raises:
            SecurityError: If the path escapes the sandbox.
        """
        safe_path = self._validate_path(path)
        with open(safe_path, "r") as f:
            return f.read()
    
    def write_file(self, path: str, content: str):
        """
        Writes content to a file safely within the sandbox.

        Args:
            path (str): The path to write to.
            content (str): The string content to write.

        Raises:
            SecurityError: If the path escapes the sandbox.
        """
        safe_path = self._validate_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(content)
    
    def delete_file(self, path: str):
        """
        Deletes a file safely within the sandbox.

        Args:
            path (str): The file to delete.

        Raises:
            SecurityError: If the path escapes the sandbox.
        """
        safe_path = self._validate_path(path)
        os.remove(safe_path)
    
    def list_files(self, directory: str) -> List[str]:
        """
        Lists files in a given directory safely within the sandbox.

        Excludes noisy directories like `.git` and `node_modules`.

        Args:
            directory (str): The directory to list.

        Returns:
            List[str]: A list of relative paths.

        Raises:
            SecurityError: If the directory escapes the sandbox.
        """
        safe_dir = self._validate_path(directory)
        
        ignore_dirs = {".git", "__pycache__", "venv", "node_modules", ".venv", ".pytest_cache", ".idea", ".vscode"}
        all_files = []
        for root, dirs, files in os.walk(safe_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ignore_dirs]
            for file in files:
                if not file.startswith('.'):
                    rel_path = os.path.relpath(os.path.join(root, file), safe_dir)
                    all_files.append(rel_path)
        return sorted(all_files)

    def edit_file(self, path: str, target_content: str, replacement_content: str) -> str:
        """
        Modifies a file by targeting a specific string block, safe to the sandbox.

        Args:
            path (str): The file to safely edit.
            target_content (str): The precise string to replace.
            replacement_content (str): The content to insert.

        Returns:
            str: A success message.

        Raises:
            SecurityError: If the path escapes the sandbox.
            ValueError: If target_content is invalid, missing, or multiple.
        """
        safe_path = self._validate_path(path)
        with open(safe_path, "r") as f:
            content = f.read()
            
        occurrences = content.count(target_content)
        if occurrences == 0:
            raise ValueError("Edit failed: target_content not found in the file.")
        elif occurrences > 1:
            raise ValueError("Edit failed: target_content matched multiple times. Ensure standard uniqueness.")
            
        new_content = content.replace(target_content, replacement_content, 1)
        with open(safe_path, "w") as f:
            f.write(new_content)
        return "File updated successfully."

    def search_codebase(self, keyword: str, directory: str = ".") -> Dict:
        """
        Executes a secure, sandbox-restricted grep search.

        Automatically caps huge shell outputs.

        Args:
            keyword (str): The keyword or regex to search for.
            directory (str, optional): The base folder to search in. Defaults to ".".

        Returns:
            Dict: Output stdout, stderr, and exit_code.
        """
        try:
            safe_dir = self._validate_path(directory)
        except Exception:
            safe_dir = self.allowed_path
            
        import subprocess
        cmd = ["grep", "-rnIE", "--exclude-dir={.git,__pycache__,venv,node_modules}", keyword, safe_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        output = result.stdout.strip()
        if len(output) > 20000:
            output = output[:20000] + "\n...[OUTPUT TRUNCATED]..."
            
        return {
            "stdout": output,
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        }
    
    def run_command(self, command: str) -> Dict:
        """
        Executes a shell command while restricting its context to the sandbox path.

        Automatically blacklists inherently destructive non-sandboxed commands like `rm -rf`.

        Args:
            command (str): The raw shell command.

        Returns:
            Dict: Stdout, stderr, and exit_code of the command.
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
        """
        Applies a unified diff/git patch inside the sandbox bounds. (Placeholder)

        Args:
            patch_text (str): The patch data to safely apply.
        """
        # TODO: Implement safe patch application
        pass


class SecurityError(Exception):
    """Raised when a security violation is attempted."""
    pass
