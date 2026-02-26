"""
Isolation backend interface for Ada.
Allows pluggable execution environments (Docker, Sandbox, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path


class IsolationBackend(ABC):
    """
    Abstract base class for isolation backends.
    Each backend provides a way to execute Ada in an isolated environment.
    """
    
    @abstractmethod
    def setup(self, task: Dict, repo_path: str) -> None:
        """
        Set up the isolated environment before execution.
        
        Args:
            task: The task dictionary to execute
            repo_path: Path to the repository snapshot
        """
        pass
    
    @abstractmethod
    def execute(self, task: Dict, repo_path: str, completed_tasks: list) -> bool:
        """
        Execute the task in the isolated environment.
        
        Args:
            task: The task dictionary to execute
            repo_path: Path to the repository snapshot
            completed_tasks: List of previously completed task IDs
        
        Returns:
            True if task completed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up the isolated environment after execution.
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Get the name of this isolation backend.
        
        Returns:
            Name of the backend (e.g., "Docker", "Sandbox")
        """
        pass
