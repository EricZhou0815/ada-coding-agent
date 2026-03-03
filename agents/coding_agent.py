import os
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
        """
        self.finished = False
        
        # Determine checkpoint path from context if available
        checkpoint_path = context.get("checkpoint_path")
        
        # Resume if checkpoint exists
        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, "r") as f:
                    state = json.load(f)
                    self.llm.set_conversation_history(state.get("messages", []))
                    tool_call_count = state.get("tool_call_count", 0)
                    logger.info(self.name, f"↻ Resuming from checkpoint: {tool_call_count} tools already executed.")
                prompt = "Please continue where you left off. Review your last action and determine the next step."
            except Exception as e:
                logger.warning(self.name, f"Failed to load checkpoint: {e}. Starting fresh.")
                self.llm.reset_conversation()
                tool_call_count = 0
                prompt = self._build_prompt(story, repo_path, context.get("validation_feedback", []), context.get("global_rules", []))
        else:
            self.llm.reset_conversation()
            tool_call_count = 0
            prompt = self._build_prompt(story, repo_path, context.get("validation_feedback", []), context.get("global_rules", []))
        
        max_tool_calls = 80
        
        while not self.finished and tool_call_count < max_tool_calls:
            try:
                response = self.llm.generate(prompt, tools=self.tools)
                
                if response.get("function_call"):
                    tool_call_count += 1
                    result = self._execute_tool(response["function_call"])
                    prompt = f"Tool execution result: {json.dumps(result)}\n\nContinue or declare 'finish' if the entire story is complete."
                
                if response.get("content"):
                    logger.thought(self.name, response['content'])
                    if "finish" in response["content"].lower():
                        self.finished = True
                        # Final save before breaking
                        if checkpoint_path:
                            self._save_checkpoint(checkpoint_path, tool_call_count)
                        break


                # Save Checkpoint after every successful interaction
                if checkpoint_path:
                    self._save_checkpoint(checkpoint_path, tool_call_count)

            except Exception as e:
                logger.error(self.name, f"Unexpected error in reasoning loop: {e}")
                # Save checkpoint one last time if possible before crashing
                if checkpoint_path:
                    self._save_checkpoint(checkpoint_path, tool_call_count)
                raise e # Propagate to orchestrator for retry/fail
        
        if tool_call_count >= max_tool_calls:
            logger.warning(self.name, f"Reached maximum tool calls ({max_tool_calls}), completing story phase.")
            self.finished = True
            
        return AgentResult(success=True, output="Coding phase completed.")

    def _save_checkpoint(self, path: str, tool_call_count: int):
        """
        Persists the agent's current state to a file using atomic writes.
        Writes to a temporary file first, then atomically replaces the target file
        to prevent corruption if the process crashes mid-write.
        """
        def json_serializable(obj):
            """Fallback strategy for non-JSON objects."""
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        try:
            state = {
                "messages": self.llm.get_conversation_history(),
                "tool_call_count": tool_call_count
            }
            # Atomic write: write to temp file, then atomically replace
            temp_path = path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(state, f, indent=2, default=json_serializable)
            # os.replace() is atomic on both POSIX and Windows
            os.replace(temp_path, path)
        except Exception as e:
            logger.warning(self.name, f"Failed to save checkpoint: {e}")


    def _execute_tool(self, function_call) -> Dict:
        """
        Executes a localized tool function dynamically based on the LLM's requested function call.
        """
        function_name = function_call.name
        try:
            arguments = json.loads(function_call.arguments)
        except json.JSONDecodeError as e:
            logger.tool_result(self.name, success=False)
            return {
                "success": False, 
                "error": f"Invalid JSON in function arguments for {function_name}: {str(e)}. Please correct the format."
            }
        
        logger.tool(self.name, function_name, arguments)
        
        # Map function calls to tool methods
        if hasattr(self.tools, function_name):
            method = getattr(self.tools, function_name)
            try:
                result = method(**arguments)
                output_len = len(str(result).encode('utf-8')) if result else 0
                logger.tool_result(self.name, success=True, result=result, output_len_bytes=output_len)
                return {"success": True, "result": result}
            except Exception as e:
                logger.tool_result(self.name, success=False, result=str(e))
                return {"success": False, "error": str(e)}
        else:
            logger.tool_result(self.name, success=False, result=f"Unknown tool: {function_name}")
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
You are Ada, a senior autonomous software engineer.

Your mission: implement the User Story end-to-end with production-level quality.

=====================================
USER STORY
=====================================
Title: {story.get('title', 'Unknown')}
Description: {story.get('description', '')}
Acceptance Criteria: {story.get('acceptance_criteria', [])}
Global Quality Rules: {rules_text}
Repo Path: {repo_path}
Validation Feedback: {validation_feedback if validation_feedback else "None"}

=====================================
CORE ENGINEERING RULES
=====================================

- Understand before coding.
- Align with existing architecture.
- Prefer minimal, safe, incremental changes.
- Avoid large refactors unless absolutely necessary.
- Tests and verification are mandatory.
- Never leave the repo broken.
- Production safety > speed.

=====================================
CONTEXT DISCIPLINE
=====================================

- Do not load unnecessary files.
- Read only relevant modules and related tests.
- Summarize architecture in ≤20 bullets before planning.
- Maintain a small working set of affected files.
- Expand context only when justified.

=====================================
WORKFLOW
=====================================

1) DISCOVERY
   - Explore structure, conventions, similar implementations.
   - Identify where feature belongs.
   - Identify build/test commands.

2) PLAN (REQUIRED before editing)
   Include:
   - Problem understanding
   - AC mapping
   - Files to modify/create
   - Test plan
   - Edge cases
   - Backward compatibility impact
   - Performance considerations
   - Risks

   If refactor required:
   - Justify clearly
   - Keep scope minimal

3) TEST STRATEGY
   - Add/update tests first when possible.
   - Tests must validate Acceptance Criteria.

4) IMPLEMENTATION
   - Small incremental edits.
   - Run tests after meaningful changes.
   - Fix failures immediately.

5) VERIFICATION (MANDATORY)
   - Run full test suite
   - Run build/lint/type checks
   - Fix all failures properly

6) PRODUCTION REVIEW (INTERNAL CHECK)
   Before finishing, evaluate:
   - How could this fail in production?
   - What edge case did I miss?
   - Is it backward compatible?
   - What breaks at scale?
   - Any performance regressions?
   - Any API contract changes?

7) FINAL CHECK
   - All Acceptance Criteria satisfied
   - Tests passing
   - No unnecessary changes
   - No debug code
   - Minimal diff size
   - Architecture preserved

Only when everything passes, include the word "finish" in your final response.

=====================================
CONSTRAINTS
=====================================

- NO GIT commands.
- You MUST make at least one change.
- You MUST run verification before finishing.
- If feature appears implemented, prove it with tests.
"""