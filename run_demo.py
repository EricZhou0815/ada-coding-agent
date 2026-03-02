#!/usr/bin/env python3
"""
Demo runner for Ada using mock LLM (no API key required).
Usage: python run_demo.py
"""

import json
import os

from agents.coding_agent import CodingAgent
from agents.validation_agent import ValidationAgent
from agents.mock_llm_client import MockLLMClient
from tools.tools import Tools
from orchestrator.task_executor import AtomicTaskExecutor


def main():
    print("=" * 60)
    print("Ada Demo - Mock LLM Mode (No API Key Required)")
    print("=" * 60)
    print()

    task_file = "tasks/example_task.json"
    repo_path = "repo_snapshot"

    # Load task
    with open(task_file) as f:
        task = json.load(f)

    print(f"Task: {task['title']}")
    print(f"Description: {task['description']}")
    print(f"Acceptance Criteria:")
    for criteria in task['acceptance_criteria']:
        print(f"  - {criteria}")
    print()

    # Initialize components with mock LLM
    tools = Tools()
    llm_client = MockLLMClient()  # Mock instead of OpenAI
    coding_agent = CodingAgent(llm_client, tools)
    validation_agent = ValidationAgent()
    executor = AtomicTaskExecutor(
        coding_agent, 
        validation_agent, 
        repo_path, 
        max_iterations=5  # Fewer iterations for demo
    )

    # Execute task
    completed_tasks = []
    try:
        print("Starting Ada's execution (simulated)...")
        print("-" * 60)
        executor.execute_task(task, completed_tasks)
        print("-" * 60)
        print("\n✅ Task completed successfully!")
        print("\nCheck the files in repo_snapshot/ to see Ada's changes!")
        print("  - repo_snapshot/app.py (updated with JWT)")
        print("  - repo_snapshot/auth.py (updated with JWT functions)")
    except Exception as e:
        print("-" * 60)
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
