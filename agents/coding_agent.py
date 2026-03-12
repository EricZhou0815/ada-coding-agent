import os
import json
from typing import Dict, List
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger

# ══════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT - Identity (rarely changes)
# ══════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are Ada, an autonomous senior software engineer.

Your responsibility is to implement software tasks inside an existing repository with production-level quality.

General principles:
- Always understand the codebase before editing
- Prefer minimal and safe modifications
- Maintain architecture consistency
- Write and update tests when necessary
- Ensure the repository remains buildable

You have access to tools for exploring files, editing code, and running tests.

Never guess file contents. Always read files before editing them.

You must explicitly output "TASK_COMPLETE" when the task is finished."""

# ══════════════════════════════════════════════════════════════════════════
# DEVELOPER PROMPT - Workflow logic (defines HOW the agent works)
# ══════════════════════════════════════════════════════════════════════════
DEVELOPER_PROMPT = """Follow this workflow strictly:

CRITICAL: Think out loud before every action. Explain your reasoning, what you're about to do, and why.

1. DISCOVERY
   - Explore repository structure and understand where the change belongs
   - Identify build/test conventions
   - Review similar existing implementations
   - Identify files to modify

2. PLAN (REQUIRED before editing)
   Create a clear plan including:
   - Problem understanding
   - Acceptance criteria mapping
   - Files to modify/create
   - Testing strategy
   - Edge cases
   - Backward compatibility impact
   - Performance considerations
   - Risks

   If refactoring is required:
   - Justify clearly why it's necessary
   - Keep scope minimal

3. TEST STRATEGY
   - Write tests first when possible (TDD approach)
   - Tests must validate all Acceptance Criteria
   - Update existing tests if behavior changes

4. IMPLEMENTATION
   - Make small incremental edits
   - Run tests after meaningful changes
   - Fix failures immediately
   - Keep changes minimal

5. VERIFICATION (MANDATORY)
   - Run full test suite
   - Run build/lint/type checks if available
   - Fix all failures properly

6. PRODUCTION REVIEW (INTERNAL CHECK)
   Before finishing, evaluate:
   - How could this fail in production?
   - What edge cases might I have missed?
   - Is it backward compatible?
   - What breaks at scale?
   - Any performance regressions?
   - Any API contract changes?

7. FINAL CHECK
   - All Acceptance Criteria satisfied
   - Tests passing
   - No unnecessary changes
   - No debug code left behind
   - Minimal diff size
   - Architecture preserved

IMPORTANT: Only output "TASK_COMPLETE" when ALL criteria are met.

CONSTRAINTS:
- NO Git commands (handled externally)
- You MUST make at least one meaningful change
- You MUST run verification before finishing
- If the feature appears already implemented, prove it with tests

CONTEXT DISCIPLINE:
- Do not load unnecessary files
- Read only relevant modules and related tests
- Summarize architecture in ≤20 bullets before planning
- Maintain a small working set of affected files
- Expand context only when justified

REASONING VISIBILITY:
- Narrate your thought process as you work
- Explain what you observe from command outputs
- State why you're choosing specific approaches
- Share your debugging reasoning when things fail"""

# Completion signal (safer than fuzzy string matching)
FINISH_SIGNAL = "TASK_COMPLETE"


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
        
        # Build the initial task prompt
        task_prompt = self._build_task_prompt(
            story, 
            repo_path, 
            context.get("validation_feedback", []), 
            context.get("global_rules", []),
            context.get("repo_intelligence", "")
        )
        
        # Resume if checkpoint exists
        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, "r") as f:
                    state = json.load(f)
                    self.llm.set_conversation_history(state.get("messages", []))
                    tool_call_count = state.get("tool_call_count", 0)
                    logger.info(self.name, f"↻ Resuming from checkpoint: {tool_call_count} tools already executed.")
                # Don't re-send system/developer prompts, just continue
                prompt = "Please continue where you left off. Review your last action and determine the next step."
            except Exception as e:
                logger.warning(self.name, f"Failed to load checkpoint: {e}. Starting fresh.")
                self.llm.reset_conversation()
                tool_call_count = 0
                # Initialize with proper message structure
                self._initialize_conversation(task_prompt)
                prompt = None  # First message already sent via initialization
        else:
            self.llm.reset_conversation()
            tool_call_count = 0
            # Initialize with proper message structure
            self._initialize_conversation(task_prompt)
            prompt = None  # First message already sent via initialization
        
        max_tool_calls = 80
        logger.set_progress(tool_call_count, max_tool_calls)
        
        # Track changes for completion summary
        files_modified = set()
        
        while not self.finished and tool_call_count < max_tool_calls:
            try:
                # Generate response (prompt is None on first iteration, task prompt already loaded)
                response = self.llm.generate(prompt or "", tools=self.tools)
                
                # ALWAYS log agent's reasoning/thoughts first (if present)
                # This captures the agent's thought process even when it makes tool calls
                if response.get("content"):
                    content = response['content']
                    
                    # Detect workflow phase from agent's thoughts
                    self._detect_and_log_phase(content, tool_call_count)
                    
                    # Log all thoughts for full visibility
                    logger.thought(self.name, content)
                    
                    # Check for completion signal
                    if FINISH_SIGNAL in content:
                        self.finished = True
                        
                        # Log completion summary
                        changes = [f"Modified {f}" for f in sorted(files_modified)] if files_modified else ["No files modified"]
                        logger.completion_summary(self.name, changes, tool_call_count)
                        
                        # Final save before breaking
                        if checkpoint_path:
                            self._save_checkpoint(checkpoint_path, tool_call_count)
                        break
                
                # Then handle tool calls (can happen in same response or separate)
                if response.get("function_call"):
                    tool_call_count += 1
                    logger.set_progress(tool_call_count, max_tool_calls)
                    
                    # If no explicit reasoning was provided, infer what agent is trying to do
                    if not response.get("content"):
                        implicit_reasoning = self._infer_reasoning_from_tool(response["function_call"])
                        if implicit_reasoning:
                            # Detect phase from implicit reasoning
                            self._detect_and_log_phase(implicit_reasoning, tool_call_count)
                            # Log the inferred thought
                            logger.thought(self.name, implicit_reasoning)
                    
                    # Track file modifications for summary
                    func_call = response["function_call"]
                    if func_call.name in {"write_file", "edit_file"}:
                        try:
                            args = json.loads(func_call.arguments)
                            if "path" in args:
                                files_modified.add(args["path"])
                        except:
                            pass
                    
                    result = self._execute_tool(response["function_call"])
                    prompt = f"Tool execution result: {json.dumps(result)}\n\nContinue or output '{FINISH_SIGNAL}' when the task is complete."
                elif not response.get("content"):
                    # No tool call AND no content - ask agent to continue
                    prompt = f"Continue with the next step or output '{FINISH_SIGNAL}' when done."
                else:
                    # Had content but no tool call - ask for next action
                    prompt = f"What's the next action? Use a tool or output '{FINISH_SIGNAL}' when complete."

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
    
    def _infer_reasoning_from_tool(self, function_call) -> str:
        """
        Generate human-readable reasoning from tool calls when LLM doesn't provide explicit thoughts.
        This ensures visibility into what the agent is doing even with function-calling models.
        """
        try:
            tool_name = function_call.name
            args = json.loads(function_call.arguments) if function_call.arguments else {}
            
            if tool_name == "list_files":
                directory = args.get("directory", "unknown")
                return f"Exploring project structure in {directory} to understand the codebase layout..."
            
            elif tool_name == "read_file":
                path = args.get("path", "unknown")
                return f"Reading {path} to understand current implementation..."
            
            elif tool_name == "search_codebase":
                query = args.get("query", "unknown")
                return f"Searching codebase for '{query}' to find relevant code patterns..."
            
            elif tool_name == "write_file":
                path = args.get("path", "unknown")
                return f"Creating new file {path} based on requirements..."
            
            elif tool_name == "edit_file":
                path = args.get("path", "unknown")
                return f"Modifying {path} to implement required changes..."
            
            elif tool_name == "delete_file":
                path = args.get("path", "unknown")
                return f"Removing {path} as it's no longer needed..."
            
            elif tool_name == "run_command":
                command = args.get("command", "unknown")
                if "test" in command.lower():
                    return f"Running test suite to verify implementation: {command}"
                elif "build" in command.lower() or "compile" in command.lower():
                    return f"Building project to check for compilation errors: {command}"
                elif "lint" in command.lower() or "format" in command.lower():
                    return f"Checking code quality: {command}"
                else:
                    return f"Executing command to verify changes: {command}"
            
            return None  # Unknown tool, let it be logged normally
            
        except Exception:
            return None  # Failed to parse, skip implicit reasoning
    
    def _detect_and_log_phase(self, thought_content: str, tool_count: int):
        """Detect workflow phase from agent's thoughts and log transitions."""
        content_lower = thought_content.lower()
        
        # Phase detection keywords (expanded to catch inferred reasoning)
        phase_keywords = {
            "DISCOVERY": ["explore", "exploring", "discovering", "discovery", "understand", "examining", "reading", "searching", "codebase layout"],
            "PLANNING": ["plan", "planning", "strategy", "approach", "will implement", "steps to", "based on requirements"],
            "IMPLEMENTING": ["implementing", "creating", "writing", "editing", "modifying", "adding", "new file", "implement required"],
            "VERIFICATION": ["testing", "verify", "verification", "running tests", "running test", "checking", "test suite", "compilation errors"],
            "REVIEW": ["review", "final check", "ensuring", "confirming", "code quality"]
        }
        
        for phase, keywords in phase_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                # Only log if phase changed
                if logger.current_phase != phase:
                    logger.phase(self.name, phase, tool_count)
                break

    def _initialize_conversation(self, task_prompt: str):
        """
        Initialize the conversation with proper prompt layering:
        1. System prompt (identity)
        2. Developer prompt (workflow)
        3. User prompt (task)
        """
        # Add system prompt
        self.llm.conversation_history.append({
            "role": "system",
            "content": SYSTEM_PROMPT
        })
        
        # Add developer/workflow prompt as a system message
        self.llm.conversation_history.append({
            "role": "system",
            "content": DEVELOPER_PROMPT
        })
        
        # Add the actual task as user message
        self.llm.conversation_history.append({
            "role": "user",
            "content": task_prompt
        })

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


    def _build_task_prompt(self, story: Dict, repo_path: str, validation_feedback: List[str], global_rules: List[str], repo_intelligence: str = "") -> str:
        """
        Constructs the task-specific prompt (USER PROMPT layer).
        
        This should ONLY contain the specific task details, not workflow or identity.
        System and developer prompts are handled separately.

        Args:
            story (Dict): The full user story configuration.
            repo_path (str): The workspace repository path.
            validation_feedback (List[str]): Any feedback provided from prior validation attempts.
            global_rules (List[str]): Quality gates to adhere to.
            repo_intelligence (str): Pre-indexed codebase context from the intelligence layer.

        Returns:
            str: The task-specific prompt containing only story details and context.
        """
        
        rules_text = "\n".join(f"  - {rule}" for rule in global_rules) if global_rules else "  None"
        
        ac_text = story.get('acceptance_criteria', [])
        if isinstance(ac_text, list):
            ac_formatted = "\n".join(f"  - {criterion}" for criterion in ac_text)
        else:
            ac_formatted = f"  {ac_text}"
        
        feedback_text = ""
        if validation_feedback:
            feedback_items = "\n".join(f"  - {fb}" for fb in validation_feedback)
            feedback_text = f"\n\nValidation Feedback:\n{feedback_items}"
        
        return f"""USER STORY

Title: {story.get('title', 'Unknown')}

Description:
{story.get('title', 'Unknown')}:{story.get('description', 'No description provided')}

Acceptance Criteria:
{ac_formatted}

Global Quality Rules:
{rules_text}

Repository Path: {repo_path}{feedback_text}

{f'Codebase Context (pre-indexed):\n{repo_intelligence}' if repo_intelligence else ''}
Begin implementation."""