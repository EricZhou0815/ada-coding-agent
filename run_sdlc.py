"""
run_sdlc.py - Ada's full SDLC runner.

Takes a GitHub repository URL and a User Story backlog, then autonomously:
  1. Clones the repository
  2. Creates a feature branch per story
  3. Plans and executes all tasks via isolated Sandboxes
  4. Commits and pushes each completed story
  5. Opens a Pull Request on GitHub

Usage:
    python3 run_sdlc.py \\
        --repo https://github.com/owner/repo \\
        --stories stories/epic_backlog.json \\
        [--base-branch main] \\
        [--workspace .ada_workspace]
"""

import os
import sys
import json
import argparse

from dotenv import load_dotenv
load_dotenv()                      # Load .env into os.environ

from config import Config
from tools.tools import Tools
from orchestrator.sdlc_orchestrator import SDLCOrchestrator
from orchestrator.rule_provider import LocalFolderRuleProvider
from utils.logger import logger


def main():
    parser = argparse.ArgumentParser(
        description="Ada – Full SDLC runner: clone → plan → code → validate → PR"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository URL (HTTPS or SSH). E.g. https://github.com/owner/repo"
    )
    parser.add_argument(
        "--stories",
        required=True,
        help="Path to a JSON file containing one or more User Stories."
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch that PRs will target (default: main)."
    )
    parser.add_argument(
        "--workspace",
        default=".ada_workspace",
        help="Local directory to use as Ada's working directory (default: .ada_workspace)."
    )
    args = parser.parse_args()

    # ── Load stories ──────────────────────────────────────────────────────────
    try:
        with open(args.stories, "r") as f:
            raw = json.load(f)
        stories = raw if isinstance(raw, list) else [raw]
    except Exception as e:
        logger.error("Startup", f"Failed to load story file '{args.stories}': {e}")
        sys.exit(1)

    # ── Header ────────────────────────────────────────────────────────────────
    provider = Config.get_llm_provider()
    logger.info("ADA", "=" * 70)
    logger.info("ADA", "Ada – Autonomous AI Software Engineering Team (SDLC Mode)")
    logger.info("ADA", "=" * 70)
    logger.info("ADA", f"Repository:  {args.repo}")
    logger.info("ADA", f"Base Branch: {args.base_branch}")
    logger.info("ADA", f"Stories:     {len(stories)}")
    logger.info("ADA", f"LLM:         {provider.upper()}")
    logger.info("ADA", f"Workspace:   {os.path.abspath(args.workspace)}")
    logger.info("ADA", "=" * 70)
    print()

    # ── Validate GitHub token ─────────────────────────────────────────────────
    if not os.getenv("GITHUB_TOKEN"):
        logger.error("Startup", "GITHUB_TOKEN is not set. Set it in your .env file.")
        sys.exit(1)

    # ── LLM + Tools ───────────────────────────────────────────────────────────
    llm_client = Config.get_llm_client()
    planning_tools = Tools()   # unrestricted read access for planning

    rule_providers = [LocalFolderRuleProvider()]

    # ── Run ───────────────────────────────────────────────────────────────────
    orchestrator = SDLCOrchestrator(
        llm_client=llm_client,
        tools=planning_tools,
        repo_url=args.repo,
        base_branch=args.base_branch,
        tasks_output_dir="tasks",
        rule_providers=rule_providers
    )

    success = orchestrator.run(stories, workspace_dir=args.workspace)

    if success:
        logger.success("SDLC run complete! Pull Requests have been opened on GitHub.")
    else:
        logger.error("SDLC", "One or more stories failed. Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
