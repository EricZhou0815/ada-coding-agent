from typing import Dict
import json
from agents.base_agent import BaseAgent, AgentResult

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

    def run(self, task: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        Validates the state of the codebase against acceptance criteria using the LLM.

        Args:
            task (Dict): The dictionary containing the atomic task definition.
            repo_path (str): The path to the repository being evaluated.
            context (Dict): the shared pipeline context.

        Returns:
            AgentResult: Result mapping containing success boolean and feedback array.
        """
        task = task or {}
        criteria = task.get("acceptance_criteria", [])

        if not criteria:
            # If no explicit criteria, we default past validation. 
            return AgentResult(success=True, output="No criteria specified")

        self.llm.reset_conversation()
        prompt = self._build_prompt(task, repo_path, criteria)

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
                print(f"ValidationAgent: {content}")

                content_upper = content.upper()
                if "PASS" in content_upper and "FAIL" not in content_upper:
                    passed = True
                    finished = True
                elif "FAIL" in content_upper:
                    passed = False
                    finished = True
                    feedback.append(content)
                else:
                    prompt = "Please finish your evaluation. Say 'PASS' if all criteria are met, or 'FAIL' if any are not met, then explain."

        if tool_call_count >= max_tool_calls:
            feedback.append("Validator reached maximum iterations and failed to conclude.")
            return AgentResult(
                success=False,
                output=feedback,
                context_updates={"validation_feedback": feedback}
            )

        return AgentResult(
            success=passed, 
            output=feedback if not passed else "All criteria met.",
            context_updates={"validation_feedback": feedback} if not passed else {}
        )

    def _execute_tool(self, function_call) -> Dict:
        """
        Executes a localized tool function dynamically based on the LLM's requested function call.
        """
        function_name = function_call.name
        arguments = json.loads(function_call.arguments)
        print(f"ValidationAgent is calling tool: {function_name}({arguments})")

        if hasattr(self.tools, function_name):
            method = getattr(self.tools, function_name)
            try:
                result = method(**arguments)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": f"Unknown tool: {function_name}"}

    def _build_prompt(self, task: Dict, repo_path: str, criteria: list) -> str:
        """
        Constructs the system prompt to instruct the Validation Agent.
        """
        return f"""
You are the autonomous Validation Agent. Your job is to verify if a software task was completed successfully.

Task Title: {task.get('title', 'Unknown')}
Acceptance Criteria: {criteria}

Repo Path: {repo_path}

Use your tools to read the code, list files, or run tests in the repository strictly to *verify* if the acceptance criteria above are met. DO NOT write or edit code.

If ALL criteria are verified as met, respond with exactly "PASS". 
If ANY criteria is not met, respond with "FAIL" followed by a detailed list of feedback and why it failed.
"""