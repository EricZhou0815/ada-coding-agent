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
        
    def setup(self, story: Dict, repo_path: str) -> None:
        """
        Set up for Docker execution.
        """
        story_id = story.get('story_id', 'unknown')
        self.container_name = f"ada_story_{story_id}"
        
        # Save story to temporary file
        temp_dir = os.path.join(os.getcwd(), ".ada_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        self.story_file_path = os.path.join(temp_dir, f"story_{story_id}.json")
        with open(self.story_file_path, 'w') as f:
            json.dump(story, f, indent=2)
        
        print(f"[Docker] Story file created: {self.story_file_path}")
        print(f"[Docker] Container name: {self.container_name}")
        
        # Verify Docker availability and build image if needed...
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except:
            raise RuntimeError("Docker not available")

        # Check image
        result = subprocess.run(["docker", "images", "-q", self.image_name], capture_output=True, text=True)
        if not result.stdout.strip():
            self._build_image()
    
    def execute(self, story: Dict, repo_path: str) -> bool:
        """
        Execute the story in a Docker container.
        """
        if not self.story_file_path:
            raise RuntimeError("Docker backend not set up.")
        
        story_path = str(Path(self.story_file_path).resolve())
        repo_path_abs = str(Path(repo_path).resolve())
        
        # Build docker run command
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{story_path}:/app/story.json:ro",
            "-v", f"{repo_path_abs}:/app/repo_snapshot:rw",
            "--name", self.container_name,
        ]
        
        # Forward API keys
        for env_var in ("GROQ_API_KEY", "OPENAI_API_KEY"):
            val = os.getenv(env_var)
            if val:
                cmd.extend(["-e", f"{env_var}={val}"])
        
        cmd.extend([
            self.image_name,
            "python3",
            "/app/docker/entrypoint.py",
            "/app/story.json",
            "/app/repo_snapshot"
        ])
        
        print(f"[Docker] Running container: {self.container_name}")
        
        try:
            result = subprocess.run(cmd, capture_output=False, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"[Docker] Execution failed: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if hasattr(self, 'story_file_path') and self.story_file_path and os.path.exists(self.story_file_path):
            os.remove(self.story_file_path)
            print(f"[Docker] Cleaned up temporary story file")
        self.container_name = None
        self.story_file_path = None
    
    def get_name(self) -> str:
        """Get backend name."""
        return "Docker"
