"""
tools/github_client.py

GitHub implementation of the VCSClient interface.
Handles PR creation, comments, CI logs using the GitHub REST API.
"""

import os
import re
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple
from utils.logger import logger
from tools.vcs_client import VCSClient, VCSClientFactory


class GitHubClient(VCSClient):
    """
    GitHub implementation of VCSClient.
    Communicates with the GitHub REST API using only the standard library.
    """

    API_BASE = "https://api.github.com"
    PLATFORM = "github"

    def __init__(self, token: Optional[str] = None):
        """
        Args:
            token: GitHub Personal Access Token with `repo` scope.
                   Falls back to GITHUB_TOKEN environment variable.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token is required. Set GITHUB_TOKEN in your .env file or pass it explicitly."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

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
        Creates a pull request on the specified repository.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name (without the owner prefix).
            head_branch: The branch containing Ada's changes.
            base_branch: The branch to merge into (e.g. "main").
            title: PR title.
            body: PR body (markdown supported).
            draft: If True, create a draft PR.

        Returns:
            The parsed GitHub PR object dict (contains html_url, number, etc.).
        """
        endpoint = f"/repos/{owner}/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
            "draft": draft
        }

        logger.info("GitHubClient", f"Creating PR: '{title}' ({head_branch} → {base_branch})")
        response = self._post(endpoint, payload)

        pr_url = response.get("html_url", "N/A")
        pr_number = response.get("number", "?")
        logger.success(f"PR #{pr_number} created: {pr_url}")
        return response

    def get_pull_requests(self, owner: str, repo: str, state: str = "open") -> list:
        """
        Lists pull requests for a repository.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            state: "open", "closed", or "all".

        Returns:
            List of PR dicts.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls?state={state}"
        return self._get(endpoint)

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Dict:
        """
        Fetches details of a specific pull request.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            pr_number: The PR number.

        Returns:
            The PR object dict.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        return self._get(endpoint)

    def create_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict:
        """
        Adds a comment to an issue or pull request.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            issue_number: The PR or issue number.
            body: Comment body (markdown supported).

        Returns:
            The created comment object dict.
        """
        endpoint = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        payload = {"body": body}
        logger.info("GitHubClient", f"Adding comment to #{issue_number}")
        return self._post(endpoint, payload)

    def get_run_jobs(self, owner: str, repo: str, run_id: int) -> Dict:
        """
        Gets the jobs for a workflow run.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            run_id: The workflow run ID.

        Returns:
            Dict containing a list of jobs.
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        return self._get(endpoint)

    def get_pipeline_jobs(self, owner: str, repo: str, pipeline_id: int) -> Dict:
        """
        VCSClient interface method - alias for get_run_jobs.
        GitHub calls pipelines "workflow runs".
        """
        return self.get_run_jobs(owner, repo, pipeline_id)

    def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        """
        Fetches the plain text logs for a specific job.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            job_id: The job ID.

        Returns:
            The raw log output as a string.
        """
        endpoint = f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
        return self._get_raw(endpoint)

    def is_collaborator(self, owner: str, repo: str, username: str) -> bool:
        """
        Checks if a user is a collaborator on the repository.
        
        This is used for security validation - only collaborators should be able
        to trigger Ada actions via PR comments.

        Args:
            owner: GitHub username or organisation.
            repo: Repository name.
            username: GitHub username to check.

        Returns:
            True if the user is a collaborator, False otherwise.
        """
        endpoint = f"/repos/{owner}/{repo}/collaborators/{username}"
        try:
            # GitHub returns 204 No Content if user IS a collaborator
            # Returns 404 if user is NOT a collaborator
            self._head(endpoint)
            return True
        except RuntimeError as e:
            if "404" in str(e):
                return False
            # Re-raise other errors (403 permission denied, etc.)
            raise

    @staticmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """
        Parses a GitHub repository URL into (owner, repo) tuple.

        Supports:
            https://github.com/owner/repo
            https://github.com/owner/repo.git
            git@github.com:owner/repo.git

        Returns:
            (owner, repo) strings.
        """
        patterns = [
            r"github\.com[:/]([^/]+)/([^/\.]+?)(?:\.git)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        raise ValueError(f"Could not parse GitHub URL: {url}")

    @staticmethod
    def get_platform_name() -> str:
        """Returns the platform name."""
        return "github"

    # ─────────────────────────────────────────────────────────────────────────
    # Internal HTTP helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = self.API_BASE + endpoint
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitHub API error {e.code}: {body}") from e

    def _get(self, endpoint: str) -> Any:
        url = self.API_BASE + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitHub API error {e.code}: {body}") from e

    def _get_raw(self, endpoint: str) -> str:
        url = self.API_BASE + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                # Some endpoints like logs might return redirects
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitHub API error {e.code}: {body}") from e

    def _head(self, endpoint: str) -> bool:
        """
        Perform a HEAD request - used for existence checks (e.g., collaborator status).
        Returns True on 2xx, raises RuntimeError on 4xx/5xx.
        """
        url = self.API_BASE + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status < 400
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GitHub API error {e.code}") from e


# Register GitHubClient with the factory
VCSClientFactory.register("github", GitHubClient)