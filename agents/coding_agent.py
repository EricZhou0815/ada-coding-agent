import json
from typing import Dict, List
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger

class CodingAgent(BaseAgent):
    """
    Ada, the autonomous LLM coding agent.
    Fully self-directed; Python does not control internal loops.
    """

    def __init__(self, llm_client, tools):
        """
        Initializes the CodingAgent.

        Args:
            llm_client (Any): An instance of an LLM client (e.g., LLMClient, MockLLMClient) capable of tool calling.
            tools (Any): An instance of a tools class (e.g., Tools, SandboxedTools) providing callable methods.
        """
        super().__init__("Coder", llm_client, tools)
        self.finished = False

    def run(self, task: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        Executes an atomic task autonomously within the given repository.

        The agent drives a reasoning loop where it prompts the LLM, processes tool calls,
        and continues until it declares the task "finished" or hits the maximum iteration count.

        Args:
            atomic_task (Dict): A dictionary representing the task to accomplish (title, description, criteria).
            repo_path (str): The filesystem path to the repository snapshot or sandbox.
            completed_tasks (List[str]): A list of previously completed task IDs for context.
            validation_feedback (List[str], optional): Feedback from the validation agent if retrying. Defaults to None.
        """
        self.finished = False
        self.llm.reset_conversation()
        
        completed_tasks = context.get("completed_tasks", [])
        validation_feedback = context.get("validation_feedback", [])
        global_rules = context.get("global_rules", [])
        
        prompt = self._build_prompt(task, repo_path, completed_tasks, validation_feedback, global_rules)
        
        # Run Ada's reasoning loop
        max_tool_calls = 10
        tool_call_count = 0
        
        while not self.finished and tool_call_count < max_tool_calls:
            response = self.llm.generate(prompt, tools=self.tools)
            
            # Check if Ada wants to use a tool
            if response.get("function_call"):
                tool_call_count += 1
                result = self._execute_tool(response["function_call"])
                prompt = f"Tool execution result: {json.dumps(result)}\n\nContinue with your task or declare 'finish' if complete."
            
            # Check if Ada declares task finished
            if response.get("content") and "finish" in response["content"].lower():
                self.finished = True
                logger.thought(self.name, response['content'])
                break
                
            if response.get("content"):
                logger.thought(self.name, response['content'])
        
        if tool_call_count >= max_tool_calls:
            logger.warning(self.name, f"Reached maximum tool calls ({max_tool_calls}), completing task.")
            self.finished = True
            
        return AgentResult(success=True, output="Coding phase completed.")

    def _execute_tool(self, function_call) -> Dict:
        """
        Executes a localized tool function dynamically based on the LLM's requested function call.

        Args:
            function_call (Any): The function call object returned by the LLM containing `name` and `arguments`.

        Returns:
            Dict: Result mapping containing `success` boolean and the `result` or `error` string.
        """
        function_name = function_call.name
        arguments = json.loads(function_call.arguments)
        
        logger.tool(self.name, function_name, arguments)
        
        # Map function calls to tool methods
        if hasattr(self.tools, function_name):
            method = getattr(self.tools, function_name)
            try:
                result = method(**arguments)
                output_len = len(str(result).encode('utf-8')) if result else 0
                logger.tool_result(self.name, success=True, output_len_bytes=output_len)
                return {"success": True, "result": result}
            except Exception as e:
                logger.tool_result(self.name, success=False)
                return {"success": False, "error": str(e)}
        else:
            logger.tool_result(self.name, success=False)
            return {"success": False, "error": f"Unknown tool: {function_name}"}

    def _build_prompt(self, atomic_task: Dict, repo_path: str, completed_tasks: List[str], validation_feedback: List[str], global_rules: List[str]) -> str:
        """
        Constructs the system prompt to instruct the LLM on its objective and constraints.

        Args:
            atomic_task (Dict): The task configuration.
            repo_path (str): The workspace repository path.
            completed_tasks (List[str]): A list of previously completed task IDs.
            validation_feedback (List[str]): Any feedback provided from prior validation attempts.
            global_rules (List[str]): Quality gates to adhere to.

        Returns:
            str: The fully constructed, templated system prompt string.
        """
        
        rules_text = "\n".join(global_rules) if global_rules else "None"
        
        return f"""
You are Ada, an autonomous software engineer AI.

Atomic Task:
{atomic_task.get('title', 'Unknown')}
Description:
{atomic_task.get('description', '')}
Dependencies: {atomic_task.get('dependencies', [])}
Acceptance Criteria: {atomic_task.get('acceptance_criteria', [])}
Global Quality Rules:
{rules_text}

Repo Path: {repo_path}
Previously Completed Tasks: {completed_tasks}
Validation Feedback: {validation_feedback if validation_feedback else "None"}

Decide how to complete this task step by step. Use your provided tools to read the codebase, make changes, and verify them.
CRITICAL: You MUST adhere to all Global Quality Rules during implementation.
CRITICAL: You MUST use the `run_command` tool to execute your code and verify it works locally before declaring 'finish'.
When finished, include the word "finish" in your response.
Act as a human engineer named Ada.
"""