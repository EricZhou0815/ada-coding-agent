"""
orchestrator/sdlc_orchestrator.py

Integrates Ada's agent pipeline into the full Software Development Lifecycle.

Workflow per story:
  1. Create a scoped feature branch:  ada/<story-id>-<slug>
  2. Run the EpicOrchestrator's planning + sequential sandbox execution
  3. Commit all changes with a structured commit message
  4. Push the branch to origin
  5. Open a Pull Request via the GitHub API using the PR template
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional

from orchestrator.epic_orchestrator import EpicOrchestrator
from orchestrator.rule_provider import RuleProvider
from tools.git_manager import GitManager
from tools.github_client import GitHubClient
from utils.logger import logger


class SDLCOrchestrator:
    """
    Top-level orchestrator that wraps the full software development lifecycle
    around Ada's agent pipeline.
    """

    PR_TEMPLATE_PATH = Path(__file__).parent.parent / ".ada" / "pr_template.md"

    def __init__(
        self,
        llm_client,
        tools,
        repo_url: str,
        base_branch: str = "main",
        tasks_output_dir: str = "tasks",
        rule_providers: Optional[List[RuleProvider]] = None,
        github_token: Optional[str] = None
    ):
        """
        Args:
            llm_client: LLM client for the PlanningAgent.
            tools: Read-only tools for the PlanningAgent.
            repo_url: GitHub HTTPS or SSH URL of the target repository.
            base_branch: Branch PRs will target (default "main").
            tasks_output_dir: Directory to persist generated task JSON files.
            rule_providers: Quality gate providers for the ValidationAgent.
            github_token: GitHub PAT. Falls back to GITHUB_TOKEN env var.
        """
        self.repo_url = repo_url
        self.base_branch = base_branch
        self.rule_providers = rule_providers or []

        # Parse owner/repo from URL for GitHub API calls
        self.gh_owner, self.gh_repo = GitHubClient.parse_repo_url(repo_url)

        self.github = GitHubClient(token=github_token)
        self.epic = EpicOrchestrator(
            llm_client=llm_client,
            tools=tools,
            tasks_output_dir=tasks_output_dir,
            rule_providers=self.rule_providers
        )

        self.git: Optional[GitManager] = None  # set after clone

    # ─────────────────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, stories: List[Dict], workspace_dir: str, clean_workspace: bool = False) -> bool:
        """
        Executes the full SDLC for a list of User Stories.

        Steps:
          1. Clone (or reuse) the repo at workspace_dir/repo
          2. For each story:
             a. Create a feature branch
             b. Execute all story tasks via EpicOrchestrator
             c. Commit + push changes
             d. Open a PR on GitHub
          3. Clean up workspace on success (or if clean_workspace is True)

        Args:
            stories: List of user story dicts.
            workspace_dir: Local directory to use as the Ada workspace.
            clean_workspace: If True, always clean up workspace (even on failure).
                             If False (default), clean on success and keep on failure
                             for debugging.

        Returns:
            True if all stories processed without unrecoverable failure.
        """
        workspace = Path(workspace_dir).resolve()
        # Scope the repo directory by owner/repo to prevent collisions
        repo_path = workspace / f"{self.gh_owner}_{self.gh_repo}"

        # ── Step 1: Clone ────────────────────────────────────────────────────
        logger.info("SDLCOrchestrator", f"📦 Bootstrapping workspace at: {workspace}")
        self.git = GitManager.clone(self.repo_url, str(repo_path))

        # Pull latest on base branch before branching
        logger.info("SDLCOrchestrator", f"Pulling latest from {self.base_branch}...")
        try:
            self.git.checkout(self.base_branch)
            self.git.pull(branch=self.base_branch)
        except Exception as e:
            logger.warning("SDLCOrchestrator", f"Could not pull latest: {e}. Continuing with current state.")

        if not isinstance(stories, list):
            stories = [stories]

        all_success = True

        for story in stories:
            story_id = story.get("story_id", "STORY-?")
            story_title = story.get("title", "Unknown story")

            logger.info("SDLCOrchestrator", f"\n{'='*70}")
            logger.info("SDLCOrchestrator", f"📖 Starting Story [{story_id}]: {story_title}")
            logger.info("SDLCOrchestrator", f"{'='*70}")

            # ── Step 2a: Create feature branch ───────────────────────────────
            branch_name = f"ada/{story_id}-{GitManager.slugify(story_title)}"
            try:
                self.git.checkout(self.base_branch)
                self.git.create_and_checkout_branch(branch_name)
            except Exception as e:
                logger.error("SDLCOrchestrator", f"Failed to create branch '{branch_name}': {e}")
                all_success = False
                continue

            # ── Step 2b: Execute story tasks ─────────────────────────────────
            story_success = self.epic.execute_stories([story], str(repo_path))

            if not story_success:
                logger.warning(
                    "SDLCOrchestrator",
                    "Story execution was not fully successful. Creating a DRAFT PR with partial work."
                )

            # ── Step 2c: Commit ───────────────────────────────────────────────
            try:
                commit_message = self._build_commit_message(story)
                self.git.commit(commit_message)
            except Exception as e:
                logger.error("SDLCOrchestrator", f"Commit failed: {e}")
                all_success = False
                continue

            # ── Step 2d: Push ─────────────────────────────────────────────────
            try:
                self.git.push(branch_name)
            except Exception as e:
                logger.error("SDLCOrchestrator", f"Push failed: {e}")
                all_success = False
                continue

            # ── Step 2e: Open PR ──────────────────────────────────────────────
            try:
                self._open_pull_request(story, branch_name, is_draft=not story_success)
            except Exception as e:
                logger.error("SDLCOrchestrator", f"PR creation failed: {e}")
                # Non-fatal — code is already pushed
                logger.warning("SDLCOrchestrator", "Branch pushed but PR was not created. Open manually.")

        # ── Workspace cleanup ─────────────────────────────────────────────
        self._cleanup_workspace(workspace, all_success, clean_workspace)

        return all_success

    # ─────────────────────────────────────────────────────────────────────────
    # Workspace lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def _cleanup_workspace(self, workspace: Path, success: bool, force: bool) -> None:
        """
        Manages workspace cleanup after an SDLC run.

        Policy:
          - On success: always clean up (workspace is no longer needed).
          - On failure: keep for debugging, unless force=True (--clean flag).
        """
        if not workspace.exists():
            return

        should_clean = success or force

        if should_clean:
            logger.info("SDLCOrchestrator", f"🧹 Cleaning up workspace: {workspace}")
            try:
                shutil.rmtree(workspace)
            except Exception as e:
                logger.warning("SDLCOrchestrator", f"Failed to clean workspace: {e}")
        else:
            logger.info(
                "SDLCOrchestrator",
                f"🔍 Workspace preserved for debugging: {workspace}"
            )
            logger.info(
                "SDLCOrchestrator",
                "   Re-run with --clean to force cleanup, or delete manually."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_commit_message(self, story: Dict) -> str:
        """
        Builds a structured, conventional-commits-style commit message.
        """
        story_id = story.get("story_id", "STORY-?")
        story_title = story.get("title", "Unknown")
        criteria = story.get("acceptance_criteria", [])

        criteria_lines = "\n".join(f"  - ✅ {c}" for c in criteria)

        return (
            f"feat({story_id}): {story_title}\n\n"
            f"Acceptance Criteria:\n{criteria_lines}\n\n"
            f"Generated autonomously by Ada."
        )

    def _open_pull_request(self, story: Dict, head_branch: str, is_draft: bool = False) -> Dict:
        """
        Fills the PR template and opens a PR via the GitHub API.
        """
        story_id = story.get("story_id", "STORY-?")
        story_title = story.get("title", "Unknown")
        criteria = story.get("acceptance_criteria", [])

        # Load PR template
        template = self._load_pr_template()

        # Build criteria checklist
        criteria_text = "\n".join(f"- [ ] {c}" for c in criteria)

        # List changed files from git
        changed = self.git.changed_files() if self.git else []
        changed_text = "\n".join(f"- `{f}`" for f in changed) if changed else "_No files tracked._"

        # Rules summary
        global_rules = []
        if self.git:
            for provider in self.rule_providers:
                global_rules.extend(provider.get_rules(self.git.repo_path))
        rules_text = "\n".join(f"- {r.splitlines()[0]}" for r in global_rules) if global_rules else "_None configured._"

        pr_body = template.format(
            story_id=story_id,
            story_title=story_title,
            acceptance_criteria=criteria_text or "_None specified._",
            task_list="_Tasks were planned and executed autonomously by Ada._",
            quality_rules=rules_text,
            changed_files=changed_text
        )

        suffix = "[Draft] " if is_draft else ""
        pr_title = f"{suffix}[Ada] {story_id}: {story_title}"

        return self.github.create_pull_request(
            owner=self.gh_owner,
            repo=self.gh_repo,
            head_branch=head_branch,
            base_branch=self.base_branch,
            title=pr_title,
            body=pr_body,
            draft=is_draft
        )

    def _load_pr_template(self) -> str:
        """Loads the PR body markdown template from disk."""
        if self.PR_TEMPLATE_PATH.exists():
            return self.PR_TEMPLATE_PATH.read_text()
        # Safe fallback if template file is missing
        return (
            "## 🤖 Ada – Automated PR\n\n"
            "**Story:** {story_title}  \n"
            "**Story ID:** {story_id}\n\n"
            "### Acceptance Criteria\n{acceptance_criteria}\n\n"
            "### Tasks\n{task_list}\n\n"
            "### Quality Rules\n{quality_rules}\n\n"
            "### Changed Files\n{changed_files}\n"
        )
