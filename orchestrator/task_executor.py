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

    def execute_story(self, story: Dict, repo_path: str) -> bool:
        """
        Executes the agent pipeline for the given User Story.
        
        Args:
            story (Dict): The user story dictionary.
            repo_path (str): Path to isolated workspace.
            
        Returns:
            bool: True if the pipeline finished successfully, False if max_retries hit.
        """
        retries = 0
        
        # Aggregate global rules
        global_rules = []
        for provider in self.rule_providers:
            provider_rules = provider.get_rules(repo_path)
            for r in provider_rules:
                global_rules.append(r)
                
        if global_rules:
            logger.info("Orchestrator", f"ℹ Loaded {len(global_rules)} Global Quality Rules.")
        
        context = {
            "global_rules": global_rules
        }

        while retries < self.max_retries:
            pipeline_success = True
            
            # Run through the pipeline of agents sequentially
            for agent in self.agents:
                logger.step(agent.name, f"Executing on story: {story.get('title')}")
                # Now passing 'story' instead of 'task'
                result = agent.run(story, repo_path, context)
                
                # Merge any new context/knowledge discovered by the agent
                if result.context_updates:
                    context.update(result.context_updates)

                if not result.success:
                    logger.error("Orchestrator", f"{agent.name} rejected the codebase.")
                    if isinstance(result.output, list):
                        for feedback in result.output:
                            logger.info("Orchestrator", f" ✗ {feedback}")
                    elif isinstance(result.output, str):
                        logger.info("Orchestrator", f" ✗ {result.output}")
                        
                    pipeline_success = False
                    break # Stop the pipeline, start from the beginning with new context
                    
            if pipeline_success:
                logger.success("Story execution completed successfully!")
                return True
                
            retries += 1
            if retries < self.max_retries:
                logger.info("Orchestrator", f"↻ Injecting feedback and restarting pipeline (Retry {retries}/{self.max_retries})...")
            
        logger.error("Orchestrator", f"Story failed after {self.max_retries} retries.")
        return False