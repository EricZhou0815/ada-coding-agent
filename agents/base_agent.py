from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class AgentResult:
    """Standardized output from any agent in the pipeline."""
    def __init__(self, success: bool, output: Any = None, context_updates: Optional[Dict[str, Any]] = None):
        self.success = success
        self.output = output
        self.context_updates = context_updates or {}

class BaseAgent(ABC):
    """
    Abstract interface for all Ada agents.
    """
    def __init__(self, name: str, llm_client, tools):
        """
        Initializes the agent.

        Args:
            name (str): The logical name of the agent (e.g., 'Coder', 'Validator').
            llm_client (Any): An instance of an LLM client capable of tool calling.
            tools (Any): An instance of a tools class providing callable methods.
        """
        self.name = name
        self.llm = llm_client
        self.tools = tools

    @abstractmethod
    def run(self, task: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        Executes the agent's specific role in the pipeline.
        
        Args:
            task (Dict): The atomic task configuration.
            repo_path (str): Path to the isolated workspace.
            context (Dict): Shared memory dictionary between agents (e.g., previous feedback, plans).
            
        Returns:
            AgentResult: Indicates success/failure and any data to pass to the next agent.
        """
        pass
