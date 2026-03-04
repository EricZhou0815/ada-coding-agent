"""
Planning Agent for Ada

Transforms unclear/incomplete user requests into complete, well-defined user stories
through conversational clarification. Focuses on behavioral requirements, not technical
implementation.
"""

import json
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Union, Optional
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger


class InteractionHandler(ABC):
    """
    Abstract interface for handling user interaction during planning.
    Allows Planning Agent to work with different UIs (CLI, API, Web).
    """
    
    @abstractmethod
    def ask_question(self, question: str) -> str:
        """
        Present a question to the user and wait for their response.
        
        Args:
            question: The question to ask the user
            
        Returns:
            User's response as a string
        """
        pass
    
    @abstractmethod
    def show_message(self, message: str) -> None:
        """
        Display a message to the user (without expecting a response).
        
        Args:
            message: The message to display
        """
        pass


class PlanningAgent(BaseAgent):
    """
    Ada's Planning Agent - clarifies user requirements before coding begins.
    
    Responsibilities:
    - Parse natural language or partial story inputs
    - Ask clarifying questions about system behavior
    - Detect ambiguities and edge cases
    - Output complete, structured user stories
    
    Does NOT:
    - Access code repositories
    - Make technical decisions
    - Ask about implementation details
    """
    
    COMPLETION_SIGNAL = "STORY_COMPLETE"
    
    def __init__(self, llm_client, max_iterations: int = 10):
        """
        Initialize the Planning Agent.
        
        Args:
            llm_client: LLM client for conversation
            max_iterations: Maximum conversation rounds (safety limit)
        """
        super().__init__("Planner", llm_client, tools=None)
        self.max_iterations = max_iterations
    
    def run(self, 
            user_input: Union[str, Dict], 
            interaction_handler: InteractionHandler,
            context: Optional[Dict] = None) -> AgentResult:
        """
        Execute the planning phase for a user story.
        
        Args:
            user_input: Natural language string or partial story dict
            interaction_handler: Handler for user interaction (CLI, API, etc.)
            context: Optional context dict for additional information
            
        Returns:
            AgentResult with success=True and structured story JSON, or
            success=False if planning failed
        """
        context = context or {}
        
        # Parse initial input
        initial_request = self._parse_input(user_input)
        
        # Build system prompt and initialize conversation
        system_prompt = self._build_system_prompt()
        
        # Reset LLM conversation and set system context
        self.llm.reset_conversation()
        self.llm.conversation_history.append({"role": "system", "content": system_prompt})
        
        iteration = 0
        start_time = self._get_timestamp()
        questions_asked = 0
        
        logger.info(self.name, f"Starting planning session for: {initial_request[:80]}...")
        
        # Conversational loop - LLM drives the flow
        while iteration < self.max_iterations:
            iteration += 1
            
            try:
                # Get LLM response (first iteration uses initial_request, subsequent use user responses)
                if iteration == 1:
                    prompt = initial_request
                else:
                    # Get user's response to LLM's question
                    try:
                        # The previous LLM response is already in conversation history
                        last_response = self.llm.conversation_history[-1].get("content", "")
                        
                        # Check if this looks like a question
                        if "?" in last_response or any(word in last_response.lower() for word in ["what", "how", "who", "when", "where", "which"]):
                            questions_asked += 1
                        
                        user_response = interaction_handler.ask_question(last_response)
                        
                        if not user_response or not user_response.strip():
                            logger.warning(self.name, "Empty response from user, prompting again")
                            prompt = "Please provide an answer to continue."
                        else:
                            prompt = user_response
                            
                    except KeyboardInterrupt:
                        logger.warning(self.name, "User interrupted planning session")
                        return AgentResult(
                            success=False, 
                            output="Planning session interrupted by user"
                        )
                
                response = self.llm.generate(prompt, tools=None)
                content = response.get("content", "") or ""
                
                logger.thought(self.name, content)
                
                # Check if LLM signals completion
                if self.COMPLETION_SIGNAL in content:
                    story = self._extract_story(content)
                    
                    if story:
                        duration = self._get_timestamp() - start_time
                        
                        # Add metadata
                        if "metadata" not in story:
                            story["metadata"] = {}
                        story["metadata"].update({
                            "source": "planning_agent",
                            "planning_agent_version": "1.0",
                            "questions_asked": questions_asked,
                            "planning_duration_seconds": duration,
                            "iterations": iteration
                        })
                        
                        # Auto-generate story_id if missing
                        if "story_id" not in story:
                            story["story_id"] = f"STORY-AUTO-{uuid.uuid4().hex[:8].upper()}"
                        
                        logger.success(self.name, f"✓ Planning complete: {story['title']}")
                        return AgentResult(success=True, output=story)
                    else:
                        logger.warning(self.name, "LLM signaled completion but story extraction failed")
                        # Ask LLM to correct the format
                        prompt = "The story format was invalid. Please output a valid JSON story."
                        continue
                
            except Exception as e:
                logger.error(self.name, f"Error in planning loop: {e}")
                return AgentResult(
                    success=False,
                    output=f"Planning failed due to error: {str(e)}"
                )
        
        # Max iterations reached
        logger.warning(self.name, f"Reached max iterations ({self.max_iterations})")
        return AgentResult(
            success=False,
            output=f"Could not complete planning within {self.max_iterations} iterations"
        )
    
    def _parse_input(self, user_input: Union[str, Dict]) -> str:
        """
        Convert user input into initial request string.
        
        Args:
            user_input: String or dict
            
        Returns:
            Formatted request string for LLM
        """
        if isinstance(user_input, str):
            return user_input
        elif isinstance(user_input, dict):
            # If already a complete story, just validate it
            if all(k in user_input for k in ["title", "description", "acceptance_criteria"]):
                return f"""
I have this user story, please verify it's complete and well-defined:

Title: {user_input.get('title')}
Description: {user_input.get('description')}
Acceptance Criteria: {json.dumps(user_input.get('acceptance_criteria'), indent=2)}

If it's complete, output STORY_COMPLETE with the story. If anything is unclear or missing, ask clarifying questions.
"""
            else:
                # Partial story
                return f"""
I have a partial user story:

{json.dumps(user_input, indent=2)}

Please help me complete it by asking clarifying questions.
"""
        else:
            return str(user_input)
    
    def _build_system_prompt(self) -> str:
        """
        Build the system prompt that guides the Planning Agent's behavior.
        
        Returns:
            System prompt string
        """
        return """You are Ada's Planning Agent, a specialist in requirements clarification.

YOUR ROLE:
Transform unclear user requests into complete, well-defined user stories that describe
system BEHAVIOR, not technical implementation.

PRINCIPLES:
1. Focus on WHAT the system should do (behavior), not HOW to build it (implementation)
2. Ask about user actions, system responses, and expected outcomes
3. Identify edge cases and error scenarios
4. Ensure acceptance criteria are specific and testable
5. Keep questions simple and non-technical
6. Be efficient - ask only what's needed for clarity

GOOD QUESTIONS (behavioral):
✓ "What action should trigger this feature?"
✓ "What should the user see after clicking submit?"
✓ "What happens if the email address is invalid?"
✓ "Who should be allowed to perform this action?"
✓ "Are there any limits or constraints?"

BAD QUESTIONS (technical - avoid these):
✗ "Should we use JWT or session tokens?"
✗ "What database table should store this?"
✗ "Should this be a REST API?"
✗ "What framework to use?"

WORKFLOW:
1. Analyze the user's request
2. Identify what's missing or ambiguous about the BEHAVIOR
3. Ask clarifying questions (you decide how many based on clarity)
4. When you have enough info, output the complete story

COMPLETION CRITERIA:
You have enough when you can write:
✓ A clear user-facing title (As a [user], I want to [action])
✓ A description of what the system should do
✓ At least 2-3 specific, testable acceptance criteria
✓ Coverage of key edge cases

OUTPUT FORMAT:
When ready, respond EXACTLY like this:

STORY_COMPLETE
```json
{
  "title": "As a [user type], I want to [action]",
  "description": "Brief description of the feature and its purpose",
  "acceptance_criteria": [
    "Specific testable criterion 1",
    "Specific testable criterion 2",
    "Specific testable criterion 3"
  ]
}
```

IMPORTANT:
- If the request is already clear and complete, you can output immediately
- For simple requests, ask 1-2 key questions
- For complex requests, break questions into logical groups (2-4 per round)
- Always think from the user's perspective, not the developer's
- Never ask about technology, architecture, or code structure

Begin by understanding the user's request and deciding if you need more information."""
    
    def _extract_story(self, content: str) -> Optional[Dict]:
        """
        Extract story JSON from LLM response.
        
        Args:
            content: LLM response content
            
        Returns:
            Story dict if found and valid, None otherwise
        """
        try:
            # Find JSON block
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
            else:
                return None
            
            story = json.loads(json_str)
            
            # Validate required fields
            required = ["title", "description", "acceptance_criteria"]
            if all(k in story for k in required):
                return story
            else:
                logger.warning(self.name, f"Story missing required fields: {[k for k in required if k not in story]}")
                return None
                
        except json.JSONDecodeError as e:
            logger.warning(self.name, f"Failed to parse story JSON: {e}")
            return None
        except Exception as e:
            logger.warning(self.name, f"Error extracting story: {e}")
            return None
    
    def _get_timestamp(self) -> int:
        """Get current timestamp in seconds."""
        import time
        return int(time.time())
