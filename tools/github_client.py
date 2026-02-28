"""
tools/github_client.py

Thin wrapper around the GitHub REST API.
Handles PR creation and lookup using a personal access token (GITHUB_TOKEN).
"""

import os
import re
import json
import urllib.request
import urllib.error
from typing import Optional, Dict
from utils.logger import logger


class GitHubClient:
    """
    Communicates with the GitHub REST API using only the standard library.
    No third-party dependencies required.
    """

    API_BASE = "https://api.github.com"

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

    @staticmethod
    def parse_repo_url(url: str):
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

    def _get(self, endpoint: str) -> list:
        url = self.API_BASE + endpoint
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"GitHub API error {e.code}: {body}") from e
