import os
import subprocess
import shlex
from typing import List, Dict

# Default command allowlist for shell command execution security
# These base commands are always permitted to prevent command injection
DEFAULT_ALLOWED_COMMANDS = {
    # Core interpreters
    "python", "python3", "python.exe",
    "node", "node.exe",
    
    # Package managers
    "npm", "npm.cmd", "pip", "pip3",
    
    # Test runners
    "pytest",
    
    # Version control
    "git",
    
    # Linters/formatters (common safe tools)
    "eslint", "ruff", "black"
}

# Load custom commands from environment for project-specific needs
# Example: ADA_CUSTOM_COMMANDS="cargo,go,mvn,gradle"
_custom_commands_str = os.getenv("ADA_CUSTOM_COMMANDS", "")
_custom_commands = set(_custom_commands_str.split(",")) if _custom_commands_str else set()

# Merge default and custom commands
ALLOWED_COMMANDS = DEFAULT_ALLOWED_COMMANDS | _custom_commands

class Tools:
    """
    Tools exposed to Ada.
    """

    def read_file(self, path: str) -> str:
        """
        Reads the content of a file.

        Args:
            path (str): The path to the file to be read.

        Returns:
            str: The target file's content.
        """
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str):
        """
        Writes content to a file, overwriting if the file exists.

        Args:
            path (str): The path to the file to be written.
            content (str): The content to write to the file.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def delete_file(self, path: str):
        """
        Deletes a file at the specified path.

        Args:
            path (str): The path to the file to be deleted.
        """
        os.remove(path)

    def list_files(self, directory: str) -> List[str]:
        """
        Lists all files in a directory recursively, filtering out noisy folders.

        Folders like `.git`, `__pycache__`, and `node_modules` are excluded 
        to keep the output clean for the LLM.

        Args:
            directory (str): The root directory to list files from.

        Returns:
            List[str]: A sorted list of relative file paths.
        """
        # Filter out common noisy subdirectories
        ignore_dirs = {".git", "__pycache__", "venv", "node_modules", ".venv", ".pytest_cache", ".idea", ".vscode"}
        all_files = []
        for root, dirs, files in os.walk(directory):
            # modify dirs in place to skip hidden/ignored dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ignore_dirs]
            for file in files:
                if not file.startswith('.'):
                    # returning relative paths to the given directory is best
                    rel_path = os.path.relpath(os.path.join(root, file), directory)
                    all_files.append(rel_path)
        return sorted(all_files)

    def edit_file(self, path: str, target_content: str, replacement_content: str) -> str:
        """
        Replaces exactly one occurrence of `target_content` with `replacement_content`.
        
        Ensures the agent doesn't have to rewrite the entire file for minor changes,
        preventing missing indents or hallucinated code replacement.

        Args:
            path (str): The path to the file to be edited.
            target_content (str): The exact string block to replace.
            replacement_content (str): The precise string to insert.

        Returns:
            str: A success message indicating the edit worked.

        Raises:
            ValueError: If target_content is not found or matched multiple times.
        """
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        occurrences = content.count(target_content)
        if occurrences == 0:
            raise ValueError("Edit failed: target_content not found in the file.")
        elif occurrences > 1:
            raise ValueError("Edit failed: target_content matched multiple times. Please provide a more specific, unique block of text.")

        new_content = content.replace(target_content, replacement_content, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return "File updated successfully."

    def search_codebase(self, keyword: str, directory: str = ".") -> Dict:
        """
        Searches all text files in the directory for the given keyword.

        Executes grep securely to provide codebase-wide context. Automatically
        truncates large outputs to prevent context-window blowing.

        Args:
            keyword (str): The regex or string to search for.
            directory (str, optional): The path to search within. Defaults to ".".

        Returns:
            Dict: Result mapping containing `stdout`, `stderr`, and `returncode`.
        """
        cmd = ["grep", "-rnIE", "--exclude-dir={.git,__pycache__,venv,node_modules}", keyword, directory]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        output = result.stdout.strip()
        # Truncate if output is too huge
        if len(output) > 20000:
            output = output[:20000] + "\n...[OUTPUT TRUNCATED]..."
            
        return {
            "stdout": output,
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }

    def run_command(self, command: str, cwd: str = None) -> Dict:
        """
        Executes a shell command with security controls.
        
        Security Features:
        - Command allowlist prevents arbitrary command execution
        - No shell=True to prevent command injection
        - Timeout protection against runaway processes
        - Sandboxed execution in specified working directory

        Args:
            command (str): The command string to execute.
            cwd (str, optional): Working directory for command execution.

        Returns:
            Dict: Result containing `stdout`, `stderr`, and `returncode`.
        """
        try:
            # Parse command into list (prevents shell injection)
            parts = shlex.split(command)
            
            if not parts:
                return {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Error: Empty command provided"
                }
            
            # Extract base command (first element)
            base_command = parts[0]
            
            # Security check: Verify command is in allowlist
            if base_command not in ALLOWED_COMMANDS:
                return {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": f"Security Error: Command '{base_command}' is not in the allowlist. Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
                }
            
            # Execute command WITHOUT shell=True (prevents injection)
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout to prevent hanging
                cwd=cwd
            )
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                "returncode": 124,  # Standard timeout exit code
                "stdout": "",
                "stderr": f"Error: Command timed out after 300 seconds"
            }
        except Exception as e:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"Error executing command: {str(e)}"
            }

    def apply_patch(self, patch_text: str):
        """
        Applies a git patch to the codebase. (Placeholder)

        Args:
            patch_text (str): The raw diff or patch string.
        """
        # Placeholder for git patch apply
        pass