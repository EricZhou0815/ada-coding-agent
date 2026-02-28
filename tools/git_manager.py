"""
tools/git_manager.py

A centralized wrapper around git CLI operations.
Provides clone, branch, commit, push, and status primitives
used by the SDLCOrchestrator to manage the full story lifecycle.
"""

import os
import subprocess
from pathlib import Path
from utils.logger import logger


class GitManager:
    """
    Manages a local git repository for Ada's SDLC integration.
    Wraps subprocess git calls with structured error handling and logging.
    """

    def __init__(self, repo_path: str):
        """
        Args:
            repo_path: Absolute path to the local git repository root.
        """
        self.repo_path = os.path.abspath(repo_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Static: Clone
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def clone(url: str, destination: str) -> "GitManager":
        """
        Clones a remote repository to a local destination directory.

        Args:
            url: The HTTPS or SSH URL of the repository.
            destination: Local directory path to clone into.

        Returns:
            A GitManager instance pointing at the cloned repo.
        """
        dest_path = os.path.abspath(destination)

        if os.path.exists(dest_path) and os.listdir(dest_path):
            logger.info("GitManager", f"Target directory already exists and is non-empty: {dest_path}")
            logger.info("GitManager", "Skipping clone — using existing directory.")
            return GitManager(dest_path)

        logger.info("GitManager", f"Cloning {url} → {dest_path}")
        result = subprocess.run(
            ["git", "clone", url, dest_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed:\n{result.stderr}")

        logger.info("GitManager", "Clone complete.")
        return GitManager(dest_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Branch management
    # ─────────────────────────────────────────────────────────────────────────

    def current_branch(self) -> str:
        """Returns the name of the currently checked-out branch."""
        result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def create_and_checkout_branch(self, branch_name: str) -> None:
        """
        Creates and checks out a new branch from the current HEAD.

        Args:
            branch_name: Name of the new branch (e.g. "ada/STORY-1-password-reset").
        """
        logger.info("GitManager", f"Creating branch: {branch_name}")
        # Check if branch already exists, if so just checkout
        check = self._run(["git", "branch", "--list", branch_name])
        if check.stdout.strip():
            logger.warning("GitManager", f"Branch '{branch_name}' already exists. Checking out.")
            self._run(["git", "checkout", branch_name], check=True)
        else:
            self._run(["git", "checkout", "-b", branch_name], check=True)

    def checkout(self, branch_name: str) -> None:
        """Checks out an existing branch."""
        self._run(["git", "checkout", branch_name], check=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Status and diff
    # ─────────────────────────────────────────────────────────────────────────

    def has_changes(self) -> bool:
        """Returns True if there are any staged or unstaged changes."""
        result = self._run(["git", "status", "--porcelain"])
        return bool(result.stdout.strip())

    def changed_files(self) -> list:
        """Returns a list of modified/added/deleted file paths."""
        result = self._run(["git", "status", "--porcelain"])
        files = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                files.append(line.strip()[2:].strip())
        return files

    # ─────────────────────────────────────────────────────────────────────────
    # Commit and push
    # ─────────────────────────────────────────────────────────────────────────

    def stage_all(self) -> None:
        """Stages all changes (equivalent to git add .)."""
        self._run(["git", "add", "."], check=True)

    def commit(self, message: str) -> None:
        """
        Creates a commit with the given message.
        No-ops gracefully if there is nothing to commit.

        Args:
            message: Full commit message string.
        """
        if not self.has_changes():
            logger.warning("GitManager", "Nothing to commit — working tree is clean.")
            return

        self.stage_all()
        result = self._run(["git", "commit", "-m", message])
        if result.returncode != 0:
            raise RuntimeError(f"git commit failed:\n{result.stderr}")

        logger.info("GitManager", f"Committed: {message.splitlines()[0]}")

    def push(self, branch_name: str, remote: str = "origin") -> None:
        """
        Pushes the given branch to the remote.

        Args:
            branch_name: Branch to push.
            remote: Remote name (default: "origin").
        """
        logger.info("GitManager", f"Pushing {branch_name} → {remote}")
        result = self._run(["git", "push", "--set-upstream", remote, branch_name])
        if result.returncode != 0:
            raise RuntimeError(f"git push failed:\n{result.stderr}")
        logger.info("GitManager", "Push complete.")

    def pull(self, remote: str = "origin", branch: str = "main") -> None:
        """Pulls latest changes from the given remote branch."""
        self._run(["git", "pull", remote, branch], check=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _run(self, cmd: list, check: bool = False) -> subprocess.CompletedProcess:
        """Runs a git command in the repo directory."""
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo_path
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        return result

    @staticmethod
    def slugify(text: str, max_len: int = 50) -> str:
        """
        Converts a story title into a git-safe branch-name slug.

        Example:
            "As a user, I want to reset my password" 
            → "as-a-user-i-want-to-reset-my-password"
        """
        import re
        slug = text.lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug.strip())
        slug = re.sub(r"-+", "-", slug)
        return slug[:max_len].rstrip("-")
