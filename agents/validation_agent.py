import json
from typing import Dict
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger

class ValidationAgent(BaseAgent):
    """
    Ada's validation agent.
    Checks rule enforcement and verifies acceptance criteria autonomously using an LLM.
    """

    def __init__(self, llm_client, tools):
        """
        Initializes the ValidationAgent.

        Args:
            llm_client (Any): An instance of an LLM client (e.g., LLMClient, MockLLMClient) capable of tool calling.
            tools (Any): An instance of a tools class (e.g., Tools, SandboxedTools) providing callable methods.
        """
        super().__init__("Validator", llm_client, tools)

    def run(self, story: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        Validates the state of the codebase against acceptance criteria using the LLM.

        Args:
            story (Dict): The dictionary containing the user story definition.
            repo_path (str): The path to the repository being evaluated.
            context (Dict): the shared pipeline context.

        Returns:
            AgentResult: Result mapping containing success boolean and feedback array.
        """
        story = story or {}
        global_rules = context.get("global_rules", [])

        if not global_rules:
            # If no global rules, we default past validation. 
            return AgentResult(success=True, output="No global quality rules specified.")

        self.llm.reset_conversation()
        prompt = self._build_prompt(story, repo_path, global_rules)

        max_tool_calls = 5
        tool_call_count = 0

        passed = False
        feedback = []
        finished = False

        while not finished and tool_call_count < max_tool_calls:
            response = self.llm.generate(prompt, tools=self.tools)

            if response.get("function_call"):
                tool_call_count += 1
                result = self._execute_tool(response["function_call"])
                prompt = f"Tool result: {json.dumps(result)}\n\nContinue validation. If done, output 'PASS' or 'FAIL' and provide your feedback."
                continue

            content = response.get("content", "")
            if content:
                logger.thought(self.name, content)
                upper_content = content.upper()
                if "PASS" in upper_content:
                    passed = True
                    finished = True
                elif "FAIL" in upper_content:
                    # Extract feedback after FAIL or just use the whole message
                    feedback.append(content)
                    passed = False
                    finished = True
                else:
                    prompt = "Please finish your evaluation. Say 'PASS' if all quality rules are met, or 'FAIL' if any are not met, then provide feedback."
            else:
                # If no content and no function call, something is wrong
                prompt = "I didn't receive an evaluation. Please state 'PASS' or 'FAIL'."
                tool_call_count += 1 # Avoid infinite loop if LLM is empty

        if tool_call_count >= max_tool_calls:
            feedback.append("Validator reached maximum iterations and failed to conclude.")
            return AgentResult(
                success=False,
                output=feedback,
                context_updates={"validation_feedback": feedback}
            )

        return AgentResult(
            success=passed, 
            output=feedback if not passed else "All global quality rules met.",
            context_updates={"validation_feedback": feedback} if not passed else {}
        )

    def _execute_tool(self, function_call) -> Dict:
        """
        Executes a localized tool function dynamically based on the LLM's requested function call.
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

    def _build_prompt(self, story: Dict, repo_path: str, global_rules: list) -> str:
        """
        Constructs the system prompt to instruct the Validation Agent.
        """
        rules_text = "\n".join(global_rules) if global_rules else "None specified."
        
        return f"""
You are the autonomous Validation Agent. Your job is to verify if a User Story was implemented successfully by ensuring the Global Quality Rules are adhered to.

Story Title: {story.get('title', 'Unknown')}
Story Description: {story.get('description', 'Unknown')}
Global Quality Rules: {rules_text}

Repo Path: {repo_path}

Use your tools to read the code, list files, or run tests in the repository strictly to *verify* if the global quality rules are met. DO NOT write or edit code.

If ALL quality rules are verified as met, respond with exactly "PASS". 
If ANY rule is not met, respond with "FAIL" followed by a detailed list of feedback and why it failed.
"""