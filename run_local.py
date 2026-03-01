#!/usr/bin/env python3
"""
Local runner for Ada - runs User Stories directly without sandbox isolation.
Usage: python run_local.py <story_file> <repo_path>
Example: python run_local.py stories/example_story.json repo_snapshot
"""

import json
import sys
import os
from pathlib import Path

from agents.coding_agent import CodingAgent
from config import Config
from tools.tools import Tools
from orchestrator.task_executor import PipelineOrchestrator
from orchestrator.rule_provider import LocalFolderRuleProvider


def main():
    if len(sys.argv) < 3:
        print("Usage: python run_local.py <story_file> <repo_path>")
        sys.exit(1)

    story_file = sys.argv[1]
    repo_path = os.path.abspath(sys.argv[2])

    if not os.path.exists(story_file):
        print(f"Error: Story file not found: {story_file}")
        sys.exit(1)
    
    if not os.path.exists(repo_path):
        os.makedirs(repo_path, exist_ok=True)

    print("=" * 60)
    print("Ada - Autonomous AI Software Engineer (Local Mode)")
    print("=" * 60)

    # Load story
    with open(story_file) as f:
        story = json.load(f)

    print(f"Story: {story.get('title', 'Untitled')}")
    print()

    # Initialize components
    tools = Tools()
    llm_client = Config.get_llm_client()
    coding_agent = CodingAgent(llm_client, tools)
    agents_pipeline = [coding_agent]
    rule_providers = [LocalFolderRuleProvider()]
    
    executor = PipelineOrchestrator(
        agents_pipeline, 
        rule_providers=rule_providers,
        max_retries=25
    )

    try:
        print("Starting Ada's execution...")
        print("-" * 60)
        success = executor.execute_story(story, repo_path)
        print("-" * 60)
        if success:
            print("\n✅ Story completed successfully!")
        else:
            print("\n❌ Story execution failed.")
    except Exception as e:
        print("-" * 60)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
