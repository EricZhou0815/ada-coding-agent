"""
Docker isolation backend for Ada.
Executes tasks in Docker containers for maximum isolation.
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List
from isolation.backend import IsolationBackend


class DockerBackend(IsolationBackend):
    """
    Docker-based isolation backend.
    Executes each task in a separate Docker container.
    """
    
    def __init__(self, image_name: str = "ada_agent_mvp"):
        """
        Initialize the Docker backend.
        
        Args:
            image_name: Name of the Docker image to use
        """
        self.image_name = image_name
        self.container_name = None
        self.task_file_path = None
        
    def setup(self, task: Dict, repo_path: str) -> None:
        """
        Set up for Docker execution.
        Saves task to temporary file for mounting.
        """
        task_id = task.get('task_id', 'unknown')
        self.container_name = f"ada_task_{task_id}"
        
        # Save task to temporary file
        task_dir = os.path.join(os.getcwd(), ".ada_temp")
        os.makedirs(task_dir, exist_ok=True)
        
        self.task_file_path = os.path.join(task_dir, f"task_{task_id}.json")
        with open(self.task_file_path, 'w') as f:
            json.dump(task, f, indent=2)
        
        print(f"[Docker] Task file created: {self.task_file_path}")
        print(f"[Docker] Container name: {self.container_name}")
        
        # Verify Docker is available
        try:
            subprocess.run(["docker", "--version"], 
                         capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("Docker is not installed or not in PATH")
        
        # Check if image exists
        result = subprocess.run(
            ["docker", "images", "-q", self.image_name],
            capture_output=True,
            text=True
        )
        
        if not result.stdout.strip():
            print(f"[Docker] Image '{self.image_name}' not found. Building...")
            self._build_image()
    
    def _build_image(self):
        """Build the Docker image."""
        dockerfile_path = os.path.join(os.getcwd(), "docker", "Dockerfile")
        
        if not os.path.exists(dockerfile_path):
            raise RuntimeError(f"Dockerfile not found at {dockerfile_path}")
        
        print(f"[Docker] Building image '{self.image_name}'...")
        
        cmd = [
            "docker", "build",
            "-t", self.image_name,
            "-f", dockerfile_path,
            "."
        ]
        
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to build Docker image")
        
        print(f"[Docker] Image '{self.image_name}' built successfully")
    
    def execute(self, task: Dict, repo_path: str, completed_tasks: List[str]) -> bool:
        """
        Execute the task in a Docker container.
        """
        if not self.task_file_path:
            raise RuntimeError("Docker backend not set up. Call setup() first.")
        
        task_path = str(Path(self.task_file_path).resolve())
        repo_path_abs = str(Path(repo_path).resolve())
        
        # Build docker run command
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{task_path}:/app/tasks/task.json:ro",
            "-v", f"{repo_path_abs}:/app/repo_snapshot:rw",
            "--name", self.container_name,
        ]
        
        # Add API key if available
        if os.getenv("OPENAI_API_KEY"):
            cmd.extend(["-e", f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}"])
        
        cmd.extend([
            self.image_name,
            "/app/tasks/task.json",
            "/app/repo_snapshot"
        ])
        
        print(f"[Docker] Running container: {self.container_name}")
        print(f"[Docker] Command: {' '.join(cmd[:8])}...")  # Show partial command
        
        try:
            result = subprocess.run(cmd, capture_output=False, text=True)
            
            if result.returncode == 0:
                print(f"[Docker] Task completed successfully")
                return True
            else:
                print(f"[Docker] Task failed with exit code {result.returncode}")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"[Docker] Execution failed: {e}")
            return False
    
    def cleanup(self) -> None:
        """
        Clean up Docker resources.
        """
        # Remove temporary task file
        if self.task_file_path and os.path.exists(self.task_file_path):
            os.remove(self.task_file_path)
            print(f"[Docker] Cleaned up task file: {self.task_file_path}")
        
        # Note: Container is removed automatically with --rm flag
        self.container_name = None
        self.task_file_path = None
    
    def get_name(self) -> str:
        """Get backend name."""
        return "Docker"
