"""
tools/vcs_client.py

Abstract interface for Version Control System (VCS) clients.
Allows Ada to work with different platforms (GitHub, GitLab, Bitbucket, etc.)
by implementing a common interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple


class VCSClient(ABC):
    """
    Abstract base class for VCS platform clients.
    
    All VCS integrations (GitHub, GitLab, Bitbucket, Azure DevOps, etc.)
    should implement this interface to enable platform-agnostic operations.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Pull/Merge Request Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_pull_request(
        self,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        draft: bool = False
    ) -> Dict:
        """
        Creates a pull request (or merge request) on the repository.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            head_branch: The branch containing changes.
            base_branch: The target branch to merge into.
            title: PR/MR title.
            body: PR/MR description (markdown supported).
            draft: If True, create as draft.

        Returns:
            Dict containing at minimum: html_url, number (or iid for GitLab)
        """
        pass

    @abstractmethod
    def get_pull_requests(self, owner: str, repo: str, state: str = "open") -> list:
        """
        Lists pull/merge requests for a repository.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            state: "open", "closed", or "all".

        Returns:
            List of PR/MR dicts with at minimum: number, head.ref, state
        """
        pass

    @abstractmethod
    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Dict:
        """
        Fetches details of a specific pull/merge request.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            pr_number: The PR/MR number (or iid for GitLab).

        Returns:
            PR/MR object dict with head.ref for branch name.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Comment Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict:
        """
        Adds a comment to an issue or pull request.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            issue_number: The PR/MR or issue number.
            body: Comment body (markdown supported).

        Returns:
            The created comment object dict.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # CI/CD Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_pipeline_jobs(self, owner: str, repo: str, pipeline_id: int) -> Dict:
        """
        Gets the jobs for a CI pipeline/workflow run.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            pipeline_id: The pipeline/workflow run ID.

        Returns:
            Dict containing a list of jobs with id, name, status/conclusion.
        """
        pass

    @abstractmethod
    def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        """
        Fetches the plain text logs for a specific job.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            job_id: The job ID.

        Returns:
            The raw log output as a string.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Access Control
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def is_collaborator(self, owner: str, repo: str, username: str) -> bool:
        """
        Checks if a user has write access to the repository.

        Args:
            owner: Repository owner/namespace.
            repo: Repository name.
            username: Username to check.

        Returns:
            True if the user has collaborator/maintainer access.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # URL Parsing
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    @abstractmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """
        Parses a repository URL into (owner, repo) tuple.

        Args:
            url: Repository URL (HTTPS or SSH format).

        Returns:
            (owner, repo) tuple.
        """
        pass

    @staticmethod
    @abstractmethod
    def get_platform_name() -> str:
        """Returns the platform name (e.g., 'github', 'gitlab')."""
        pass


class VCSClientFactory:
    """
    Factory for creating VCS clients based on configuration.
    """
    
    _clients: Dict[str, type] = {}
    
    @classmethod
    def register(cls, platform: str, client_class: type):
        """Register a VCS client implementation."""
        cls._clients[platform.lower()] = client_class
    
    @classmethod
    def create(cls, platform: str = None, **kwargs) -> VCSClient:
        """
        Create a VCS client for the specified platform.
        
        Args:
            platform: Platform name ("github", "gitlab", etc.)
                     If None, reads from VCS_PLATFORM env var (default: "github")
            **kwargs: Additional arguments passed to the client constructor
            
        Returns:
            Configured VCSClient instance
        """
        import os
        
        if platform is None:
            platform = os.getenv("VCS_PLATFORM", "github")
        
        platform = platform.lower()
        
        if platform not in cls._clients:
            available = ", ".join(cls._clients.keys()) or "none"
            raise ValueError(
                f"Unknown VCS platform: '{platform}'. "
                f"Available platforms: {available}"
            )
        
        return cls._clients[platform](**kwargs)
    
    @classmethod
    def available_platforms(cls) -> list:
        """Returns list of registered platform names."""
        return list(cls._clients.keys())
