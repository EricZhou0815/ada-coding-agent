#!/usr/bin/env python3
"""
Local runner for Ada - runs tasks without Docker.
Usage: python run_local.py <task_file> <repo_path>
Example: python run_local.py tasks/example_task.json repo_snapshot
"""

import json
import sys
import os
from pathlib import Path

from agents.coding_agent import AdaCodingAgent
from agents.validation_agent import AdaValidationAgent
from agents.llm_client import OpenAIClient
from tools.tools import AdaTools
from orchestrator.task_executor import AtomicTaskExecutor


def main():
    if len(sys.argv) < 3:
        print("Usage: python run_local.py <task_file> <repo_path>")
        print("Example: python run_local.py tasks/example_task.json repo_snapshot")
        sys.exit(1)

    task_file = sys.argv[1]
    repo_path = sys.argv[2]

    # Validate paths
    if not os.path.exists(task_file):
        print(f"Error: Task file not found: {task_file}")
        sys.exit(1)
    
    if not os.path.exists(repo_path):
        print(f"Error: Repo path not found: {repo_path}")
        print(f"Creating directory: {repo_path}")
        os.makedirs(repo_path, exist_ok=True)

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: $env:OPENAI_API_KEY='your-api-key-here'")
        sys.exit(1)

    print("=" * 60)
    print("Ada - Autonomous AI Software Engineer")
    print("=" * 60)
    print(f"Task file: {task_file}")
    print(f"Repo path: {repo_path}")
    print()

    # Load task
    with open(task_file) as f:
        task = json.load(f)

    print(f"Task: {task['title']}")
    print(f"Description: {task['description']}")
    print()

    # Initialize components
    tools = AdaTools()
    llm_client = OpenAIClient()
    coding_agent = AdaCodingAgent(llm_client, tools)
    validation_agent = AdaValidationAgent()
    executor = AtomicTaskExecutor(
        coding_agent, 
        validation_agent, 
        repo_path, 
        max_iterations=25
    )

    # Execute task
    completed_tasks = []
    try:
        print("Starting Ada's execution...")
        print("-" * 60)
        executor.execute_task(task, completed_tasks)
        print("-" * 60)
        print("\n✅ Task completed successfully!")
    except Exception as e:
        print("-" * 60)
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
