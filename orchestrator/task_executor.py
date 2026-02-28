from typing import List, Dict
from agents.base_agent import BaseAgent

class PipelineOrchestrator:
    """
    Executes a chain of Agents dynamically.
    Instead of hardcoding agents, it passes context through a pipeline and retries based on failures.
    """
    def __init__(self, agents: List[BaseAgent], max_retries: int = 5):
        """
        Initializes the PipelineOrchestrator.
        
        Args:
            agents (List[BaseAgent]): An ordered list of agents to execute.
            max_retries (int): Maximum number of pipeline pipeline loops before failing.
        """
        self.agents = agents
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
        context = {
            "completed_tasks": completed_tasks or []
        }

        while retries < self.max_retries:
            pipeline_success = True
            
            # Run through the pipeline of agents sequentially
            for agent in self.agents:
                print(f"[{agent.name}] Starting execution...")
                result = agent.run(task, repo_path, context)
                
                # Merge any new context/knowledge discovered by the agent
                if result.context_updates:
                    context.update(result.context_updates)

                if not result.success:
                    print(f"[{agent.name}] Failed. Triggering pipeline retry cycle.")
                    pipeline_success = False
                    break # Stop the pipeline, start from the beginning with new context
                    
            if pipeline_success:
                print("Pipeline completed successfully!")
                if task.get("task_id") and isinstance(completed_tasks, list):
                    completed_tasks.append(task["task_id"])
                return True
                
            retries += 1
            print(f"[Orchestrator] Retry cycle {retries}/{self.max_retries}")
            
        print(f"Pipeline failed after {self.max_retries} retries.")
        return False