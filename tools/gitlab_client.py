"""
tools/gitlab_client.py

GitLab implementation of the VCSClient interface.
Handles Merge Request creation, comments, CI logs using the GitLab REST API.
"""

import os
import re
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, Tuple
from utils.logger import logger
from tools.vcs_client import VCSClient, VCSClientFactory


class GitLabClient(VCSClient):
    """
    GitLab implementation of VCSClient.
    Communicates with the GitLab REST API using only the standard library.
    
    Note: GitLab uses "Merge Requests" instead of "Pull Requests",
    and "project ID" or "namespace/project" instead of "owner/repo".
    """

    PLATFORM = "gitlab"

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        """
        Args:
            token: GitLab Personal Access Token with `api` scope.
                   Falls back to GITLAB_TOKEN environment variable.
            base_url: GitLab instance URL (default: https://gitlab.com).
                      Falls back to GITLAB_URL environment variable.
        """
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.api_base = (base_url or os.getenv("GITLAB_URL", "https://gitlab.com")).rstrip("/") + "/api/v4"
        
        if not self.token:
            raise ValueError(
                "GitLab token is required. Set GITLAB_TOKEN in your .env file or pass it explicitly."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Pull/Merge Request Operations
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
        Creates a merge request on the specified project.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/merge_requests"
        
        payload = {
            "source_branch": head_branch,
            "target_branch": base_branch,
            "title": f"Draft: {title}" if draft else title,
            "description": body,
        }

        logger.info("GitLabClient", f"Creating MR: '{title}' ({head_branch} → {base_branch})")
        response = self._post(endpoint, payload)

        # Normalize response to match GitHub format for compatibility
        mr_url = response.get("web_url", "N/A")
        mr_iid = response.get("iid", "?")
        logger.success(f"MR !{mr_iid} created: {mr_url}")
        
        # Add GitHub-compatible fields
        response["html_url"] = response.get("web_url")
        response["number"] = response.get("iid")
        return response

    def get_pull_requests(self, owner: str, repo: str, state: str = "open") -> list:
        """
        Lists merge requests for a project.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        
        # Map GitHub state names to GitLab
        gitlab_state = {"open": "opened", "closed": "closed", "all": "all"}.get(state, "opened")
        
        endpoint = f"/projects/{encoded_path}/merge_requests?state={gitlab_state}"
        mrs = self._get(endpoint)
        
        # Normalize to GitHub format
        for mr in mrs:
            mr["number"] = mr.get("iid")
            mr["html_url"] = mr.get("web_url")
            mr["head"] = {"ref": mr.get("source_branch")}
            mr["base"] = {"ref": mr.get("target_branch")}
            mr["state"] = "open" if mr.get("state") == "opened" else mr.get("state")
        
        return mrs

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Dict:
        """
        Fetches details of a specific merge request.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/merge_requests/{pr_number}"
        
        mr = self._get(endpoint)
        
        # Normalize to GitHub format
        mr["number"] = mr.get("iid")
        mr["html_url"] = mr.get("web_url")
        mr["head"] = {"ref": mr.get("source_branch")}
        mr["base"] = {"ref": mr.get("target_branch")}
        
        return mr

    # ─────────────────────────────────────────────────────────────────────────
    # Comment Operations
    # ─────────────────────────────────────────────────────────────────────────

    def create_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict:
        """
        Adds a note (comment) to a merge request.
        GitLab uses "notes" for MR comments.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/merge_requests/{issue_number}/notes"
        
        payload = {"body": body}
        logger.info("GitLabClient", f"Adding comment to !{issue_number}")
        return self._post(endpoint, payload)

    # ─────────────────────────────────────────────────────────────────────────
    # CI/CD Operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_pipeline_jobs(self, owner: str, repo: str, pipeline_id: int) -> Dict:
        """
        Gets the jobs for a CI pipeline.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/pipelines/{pipeline_id}/jobs"
        
        jobs = self._get(endpoint)
        
        # Normalize to GitHub format
        normalized_jobs = []
        for job in jobs:
            normalized_jobs.append({
                "id": job.get("id"),
                "name": job.get("name"),
                "conclusion": job.get("status"),  # GitLab: failed, success, etc.
                "status": job.get("status"),
            })
        
        return {"jobs": normalized_jobs}

    def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        """
        Fetches the plain text logs for a specific job.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/jobs/{job_id}/trace"
        return self._get_raw(endpoint)

    # ─────────────────────────────────────────────────────────────────────────
    # Access Control
    # ─────────────────────────────────────────────────────────────────────────

    def is_collaborator(self, owner: str, repo: str, username: str) -> bool:
        """
        Checks if a user is a member of the project with at least Developer access.
        """
        project_path = f"{owner}/{repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")
        endpoint = f"/projects/{encoded_path}/members/all"
        
        try:
            members = self._get(endpoint)
            for member in members:
                if member.get("username") == username:
                    # Access levels: 10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner
                    return member.get("access_level", 0) >= 30
            return False
        except RuntimeError as e:
            if "404" in str(e):
                return False
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # URL Parsing
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """
        Parses a GitLab repository URL into (namespace, project) tuple.

        Supports:
            https://gitlab.com/namespace/project
            https://gitlab.com/namespace/project.git
            https://gitlab.example.com/group/subgroup/project
            git@gitlab.com:namespace/project.git

        Returns:
            (namespace, project) strings.
            For nested groups, namespace includes the full path (e.g., "group/subgroup").
        """
        # Match gitlab URLs - handle nested groups
        patterns = [
            r"gitlab[^/]*[:/](.+)/([^/\.]+?)(?:\.git)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        raise ValueError(f"Could not parse GitLab URL: {url}")

    @staticmethod
    def get_platform_name() -> str:
        """Returns the platform name."""
        return "gitlab"

    # ─────────────────────────────────────────────────────────────────────────
    # Internal HTTP helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = self.api_base + endpoint
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitLab API error {e.code}: {body}") from e

    def _get(self, endpoint: str) -> Any:
        url = self.api_base + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitLab API error {e.code}: {body}") from e

    def _get_raw(self, endpoint: str) -> str:
        url = self.api_base + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitLab API error {e.code}: {body}") from e


# Register GitLabClient with the factory
VCSClientFactory.register("gitlab", GitLabClient)
