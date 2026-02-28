import json
from typing import Dict, List
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger

class PlanningAgent(BaseAgent):
    """
    Acts as a Technical Product Manager.
    Breaks down high-level User Stories into an array of atomic tasks based on the current codebase.
    """

    def __init__(self, llm_client, tools):
        """
        Initializes the PlanningAgent.
        """
        super().__init__("Planner", llm_client, tools)

    def run(self, story: Dict, repo_path: str, context: Dict = None) -> AgentResult:
        """
        Explores the codebase to break a story into structured JSON tasks.

        Args:
            story (Dict): The user story definition.
            repo_path (str): The isolated workspace path to explore.
            context (Dict): the shared pipeline context.
        """
        self.llm.reset_conversation()
        prompt = self._build_prompt(story, repo_path)

        max_tool_calls = 5
        tool_call_count = 0
        tasks_json_output = None

        while not tasks_json_output and tool_call_count < max_tool_calls:
            response = self.llm.generate(prompt, tools=self.tools)

            if response.get("function_call"):
                tool_call_count += 1
                result = self._execute_tool(response["function_call"])
                prompt = f"Tool result: {json.dumps(result)}\n\nContinue exploring or output your final JSON task list inside ```json blocks."
                continue

            content = response.get("content", "")
            if content:
                logger.thought(self.name, content)
                
                # Attempt to extract JSON from the thought
                extracted_json_str = None
                if "```json" in content:
                    extracted_json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    extracted_json_str = content.split("```")[1].split("```")[0].strip()
                else:
                    # In case the agent just dumps raw JSON without markdown blocks
                    s = content.strip()
                    if s.startswith("[") and s.endswith("]"):
                        extracted_json_str = s

                if extracted_json_str:
                    try:
                        tasks_json_output = json.loads(extracted_json_str)
                        # Validate we actually got an array of dicts containing a 'title'
                        if isinstance(tasks_json_output, list) and len(tasks_json_output) > 0 and 'title' in tasks_json_output[0]:
                            break
                        else:
                            tasks_json_output = None
                            prompt = "The JSON provided was not a valid list of Task objects. Please output a JSON array of objects conforming to the schema."
                    except Exception as e:
                        prompt = f"Failed to parse JSON: {e}. Please correct formatting and try again. Output strictly inside ```json blocks."
                else:
                    prompt = "Please finish your system design. Output a single array of JSON task objects inside ```json blocks."

        if not tasks_json_output:
            err = "Planner reached maximum iterations or failed to produce valid JSON."
            logger.error(self.name, err)
            return AgentResult(success=False, output=err)

        logger.success(f"Successfully generated {len(tasks_json_output)} atomic tasks.")
        return AgentResult(
            success=True, 
            output="Story breakdown complete.",
            context_updates={"generated_tasks": tasks_json_output}
        )

    def _execute_tool(self, function_call) -> Dict:
        function_name = function_call.name
        arguments = json.loads(function_call.arguments)
        
        logger.tool(self.name, function_name, arguments)
        
        # Only allow read-only tools for planning!
        allowed_tools = ["search_codebase", "list_files", "read_file"]
        
        if function_name not in allowed_tools:
            err = f"Tool '{function_name}' is not allowed for PlanningAgent."
            logger.tool_result(self.name, success=False)
            return {"success": False, "error": err}
            
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

    def _build_prompt(self, story: Dict, repo_path: str) -> str:
        return f"""
You are the Technical Product Manager (Planning Agent) for Ada.
Your goal is to break down a high-level User Story into a strict chronological series of atomic tasks for an architecture.

User Story:
Title: {story.get('title', 'Unknown')}
Description:
{story.get('description', '')}
Acceptance Criteria:
{story.get('acceptance_criteria', [])}

Repository Path: {repo_path}

Instructions:
1. Use your tools (`search_codebase`, `list_files`, `read_file`) to explore the current state of the repo path.
2. Determine what code currently exists and what is missing to fulfill the user story.
3. Design a system architecture and break it down into small, actionable atomic tasks.
4. Output your FINAL answer strictly as a JSON array enclosed by ```json and ``` markers.

The JSON array must contain objects matching this exact schema:
[
  {{
    "task_id": "STORY1-T1",
    "title": "Short descriptive title",
    "description": "Implementation details.",
    "dependencies": [], // IDs of tasks that must execute first
    "acceptance_criteria": ["...", "..."] 
  }}
]
"""
