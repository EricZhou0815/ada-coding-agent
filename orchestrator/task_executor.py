from typing import List, Dict, Optional
from agents.base_agent import BaseAgent
from orchestrator.rule_provider import RuleProvider
from utils.logger import logger

class PipelineOrchestrator:
    """
    Executes a chain of Agents dynamically.
    Instead of hardcoding agents, it passes context through a pipeline and retries based on failures.
    """
    def __init__(self, agents: List[BaseAgent], rule_providers: Optional[List[RuleProvider]] = None, max_retries: int = 5):
        """
        Initializes the PipelineOrchestrator.
        
        Args:
            agents (List[BaseAgent]): An ordered list of agents to execute.
            rule_providers (List[RuleProvider], optional): Providers to fetch global rules for the pipeline context.
            max_retries (int): Maximum number of pipeline pipeline loops before failing.
        """
        self.agents = agents
        self.rule_providers = rule_providers or []
        self.max_retries = max_retries

    def execute_task(self, task: Dict, repo_path: str, completed_tasks: List[str] = None) -> bool:
        """
        Executes the agent pipeline for the given task.
        
        Args:
            task (Dict): The atomic task dictionary.
            repo_path (str): Path to isolated workspace.
            completed_tasks (List[str]): List of previous completed task IDs.
            
        Returns:
            bool: True if the pipeline finished successfully, False if max_retries hit.
        """
        retries = 0
        
        # Aggregate global rules
        global_rules = []
        for provider in self.rule_providers:
            # We assume RuleProvider.get_rules returns rules starting with "Rule from..."
            provider_rules = provider.get_rules(repo_path)
            for r in provider_rules:
                global_rules.append(r)
                
        if global_rules:
            logger.info("Orchestrator", f"ℹ Loaded {len(global_rules)} Global Quality Rules.")
            for r in global_rules:
                # Truncate string for the console
                first_line = r.split('\n')[0]
                logger.info("Orchestrator", f"  - {first_line}")
                
        context = {
            "completed_tasks": completed_tasks or [],
            "global_rules": global_rules
        }

        while retries < self.max_retries:
            pipeline_success = True
            
            # Run through the pipeline of agents sequentially
            for agent in self.agents:
                logger.step(agent.name, "Starting execution...")
                result = agent.run(task, repo_path, context)
                
                # Merge any new context/knowledge discovered by the agent
                if result.context_updates:
                    context.update(result.context_updates)

                if not result.success:
                    logger.error("Orchestrator", f"{agent.name} rejected the codebase.")
                    # Explicitly list the reasons so the user can see *why* the pipeline failed!
                    if isinstance(result.output, list):
                        for feedback in result.output:
                            logger.info("Orchestrator", f" ✗ {feedback}")
                    elif isinstance(result.output, str):
                        logger.info("Orchestrator", f" ✗ {result.output}")
                        
                    pipeline_success = False
                    break # Stop the pipeline, start from the beginning with new context
                    
            if pipeline_success:
                logger.success("Pipeline completed successfully!")
                if task.get("task_id") and isinstance(completed_tasks, list):
                    completed_tasks.append(task["task_id"])
                return True
                
            retries += 1
            if retries < self.max_retries:
                logger.info("Orchestrator", f"↻ Injecting feedback into context and restarting pipeline (Retry {retries}/{self.max_retries})...")
            
        logger.error("Orchestrator", f"Pipeline failed after {self.max_retries} retries.")
        return False