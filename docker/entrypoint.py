#!/usr/bin/env python3

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.coding_agent import CodingAgent
from agents.validation_agent import ValidationAgent
from config import Config
from tools.tools import Tools
from orchestrator.task_executor import AtomicTaskExecutor

def main():
    task_file = sys.argv[1]
    repo_path = sys.argv[2]

    llm_client = Config.get_llm_client()
    coding_agent = CodingAgent(llm_client, tools)
    validation_agent = ValidationAgent()
    executor = AtomicTaskExecutor(coding_agent, validation_agent, repo_path, max_iterations=25)

    with open(task_file) as f:
        task = json.load(f)

    completed_tasks = []
    executor.execute_task(task, completed_tasks)

if __name__ == "__main__":
    main()