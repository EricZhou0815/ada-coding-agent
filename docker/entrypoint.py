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
from orchestrator.task_executor import PipelineOrchestrator
from orchestrator.rule_provider import LocalFolderRuleProvider

def main():
    task_file = sys.argv[1]
    repo_path = sys.argv[2]

    llm_client = Config.get_llm_client()
    coding_agent = CodingAgent(llm_client, tools)
    validation_agent = ValidationAgent(llm_client, tools)
    agents_pipeline = [coding_agent, validation_agent]
    rule_providers = [LocalFolderRuleProvider()]
    executor = PipelineOrchestrator(
        agents_pipeline, 
        rule_providers=rule_providers, 
        max_retries=25
    )

    with open(task_file) as f:
        task = json.load(f)

    completed_tasks = []
    executor.execute_task(task, repo_path, completed_tasks)

if __name__ == "__main__":
    main()