from typing import List, Dict
import json

class AdaCodingAgent:
    """
    Ada, the autonomous LLM coding agent.
    Fully self-directed; Python does not control internal loops.
    """

    def __init__(self, llm_client, tools):
        self.llm = llm_client
        self.tools = tools
        self.finished = False

    def run(self, atomic_task: Dict, repo_path: str,
            completed_tasks: List[str], validation_feedback: List[str] = None):
        """
        Execute atomic task autonomously as Ada.
        """
        self.finished = False
        self.llm.reset_conversation()
        
        prompt = self._build_prompt(atomic_task, repo_path, completed_tasks, validation_feedback)
        
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
                print(f"Ada: {response['content']}")
                break
                
            if response.get("content"):
                print(f"Ada: {response['content']}")
        
        if tool_call_count >= max_tool_calls:
            print(f"Ada: Reached maximum tool calls ({max_tool_calls}), completing task.")
            self.finished = True

    def _execute_tool(self, function_call) -> Dict:
        """Execute a tool call and return the result."""
        function_name = function_call.name
        arguments = json.loads(function_call.arguments)
        
        print(f"Ada is calling tool: {function_name}({arguments})")
        
        # Map function calls to tool methods
        if hasattr(self.tools, function_name):
            method = getattr(self.tools, function_name)
            try:
                result = method(**arguments)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": f"Unknown tool: {function_name}"}

    def _build_prompt(self, atomic_task, repo_path, completed_tasks, validation_feedback):
        return f"""
You are Ada, an autonomous software engineer AI.

Atomic Task:
{atomic_task['title']}
Description:
{atomic_task['description']}
Dependencies: {atomic_task.get('dependencies', [])}
Acceptance Criteria: {atomic_task.get('acceptance_criteria', [])}

Repo Path: {repo_path}
Previously Completed Tasks: {completed_tasks}
Validation Feedback: {validation_feedback if validation_feedback else "None"}

You have access to tools via function calling:
- read_file(path): Read a file
- write_file(path, content): Write to a file
- delete_file(path): Delete a file
- list_files(directory): List files in directory
- run_command(command): Execute shell command

Decide how to complete this task step by step.
When finished, include the word "finish" in your response.
Act as a human engineer named Ada.
"""