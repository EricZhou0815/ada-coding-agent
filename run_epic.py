"""
run_epic.py - Ada's Epic-level runner.

Reads a JSON file containing one or more User Stories, uses the PlanningAgent
to break each story into atomic tasks, persists those tasks to disk, then
executes them sequentially through isolated Sandboxes.

Usage:
    python3 run_epic.py stories/epic_backlog.json repo_snapshot
"""

import os
import sys
import json
import argparse
from config import Config
from tools.tools import Tools
from orchestrator.epic_orchestrator import EpicOrchestrator
from orchestrator.rule_provider import LocalFolderRuleProvider
from utils.logger import logger


def main():
    parser = argparse.ArgumentParser(description="Run Ada on a User Story backlog.")
    parser.add_argument("story_file", help="Path to a JSON file containing an array of User Stories.")
    parser.add_argument("repo_path", help="Path to the repository to modify.")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)

    # Load stories — supports both a single story object and an array
    try:
        with open(args.story_file, "r") as f:
            raw = json.load(f)
        stories = raw if isinstance(raw, list) else [raw]
    except Exception as e:
        logger.error("Startup", f"Failed to load story file: {e}")
        sys.exit(1)

    # Header
    provider = Config.get_llm_provider()
    logger.info("ADA", "="*70)
    logger.info("ADA", "Ada - Autonomous AI Story Engineering Team")
    logger.info("ADA", "="*70)
    logger.info("ADA", f"LLM Mode:    {provider.upper()}")
    logger.info("ADA", f"Stories:     {len(stories)} user stories")
    logger.info("ADA", f"Repo Path:   {repo_path}")
    logger.info("ADA", "="*70)
    print()

    # Build LLM client + read-only planning tools
    llm_client = Config.get_llm_client()
    planning_tools = Tools()   # Tools() with no path = unrestricted (for planning only)

    rule_providers = [LocalFolderRuleProvider()]

    orchestrator = EpicOrchestrator(
        llm_client=llm_client,
        tools=planning_tools,
        tasks_output_dir="tasks",
        rule_providers=rule_providers
    )

    success = orchestrator.execute_stories(stories, repo_path)

    if success:
        logger.success("Epic complete! Check your repo for Ada's changes.")
    else:
        logger.error("Epic", "Epic failed. Review the output above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
