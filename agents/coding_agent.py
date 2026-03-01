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

    def run(self, story: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        Executes a full User Story autonomously within the given repository.

        The agent drives a reasoning loop where it prompts the LLM, processes tool calls,
        and continues until it declares the story "finished" or hits the maximum iteration count.

        Args:
            story (Dict): A dictionary representing the User Story (title, description, criteria).
            repo_path (str): The filesystem path to the repository snapshot or sandbox.
            context (Dict): Global context including completed stories, rules, etc.
        """
        self.finished = False
        self.llm.reset_conversation()
        
        validation_feedback = context.get("validation_feedback", [])
        global_rules = context.get("global_rules", [])
        
        prompt = self._build_prompt(story, repo_path, validation_feedback, global_rules)
        
        # Run Ada's reasoning loop
        # Increased for full story execution
        max_tool_calls = 80
        tool_call_count = 0
        
        while not self.finished and tool_call_count < max_tool_calls:
            response = self.llm.generate(prompt, tools=self.tools)
            
            # Check if Ada wants to use a tool
            if response.get("function_call"):
                tool_call_count += 1
                result = self._execute_tool(response["function_call"])
                prompt = f"Tool execution result: {json.dumps(result)}\n\nContinue or declare 'finish' if the entire story is complete."
            
            # Check if Ada declares story finished
            if response.get("content") and "finish" in response["content"].lower():
                self.finished = True
                logger.thought(self.name, response['content'])
                break
                
            if response.get("content"):
                logger.thought(self.name, response['content'])
        
        if tool_call_count >= max_tool_calls:
            logger.warning(self.name, f"Reached maximum tool calls ({max_tool_calls}), completing story phase.")
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

    def _build_prompt(self, story: Dict, repo_path: str, validation_feedback: List[str], global_rules: List[str]) -> str:
        """
        Constructs the system prompt to instruct the LLM on its objective and constraints.

        Args:
            story (Dict): The full user story configuration.
            repo_path (str): The workspace repository path.
            validation_feedback (List[str]): Any feedback provided from prior validation attempts.
            global_rules (List[str]): Quality gates to adhere to.

        Returns:
            str: The fully constructed, templated system prompt string.
        """
        
        rules_text = "\n".join(global_rules) if global_rules else "None"
        
        return f"""
You are Ada, an autonomous software engineer AI. Your goal is to implement a full User Story end-to-end.

User Story:
{story.get('title', 'Unknown')}
Description:
{story.get('description', '')}
Acceptance Criteria: {story.get('acceptance_criteria', [])}

Global Quality Rules:
{rules_text}

Repo Path: {repo_path}
Validation Feedback: {validation_feedback if validation_feedback else "None"}

WORKFLOW:
1. Explore the codebase to understand the existing architecture.
2. Formulate an implementation plan.
3. Use your tools to execute the plan step-by-step.
4. Use the `run_command` tool to run tests and verify your changes.
5. If you break something, fix it immediately.

CRITICAL: You MUST adhere to all Global Quality Rules.
CRITICAL: You MUST verify all changes with tests before finishing.
When the entire User Story is implemented and verified, include the word "finish" in your response.
Act as a human engineer named Ada.
"""