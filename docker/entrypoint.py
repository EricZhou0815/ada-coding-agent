#!/usr/bin/env python3

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.coding_agent import AdaCodingAgent
from agents.validation_agent import AdaValidationAgent
from agents.llm_client import OpenAIClient
from tools.tools import AdaTools
from orchestrator.task_executor import AtomicTaskExecutor

def main():
    task_file = sys.argv[1]
    repo_path = sys.argv[2]

    tools = AdaTools()
    llm_client = OpenAIClient()  # Will use OPENAI_API_KEY from environment
    coding_agent = AdaCodingAgent(llm_client, tools)
    validation_agent = AdaValidationAgent()
    executor = AtomicTaskExecutor(coding_agent, validation_agent, repo_path, max_iterations=25)

    with open(task_file) as f:
        task = json.load(f)

    completed_tasks = []
    executor.execute_task(task, completed_tasks)

if __name__ == "__main__":
    main()