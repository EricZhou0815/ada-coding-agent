"""
planning/planner_agent.py

Enhanced Planning Agent for Phase 3.
Converts user stories into structured ImplementationPlans with atomic tasks and dependencies.
Uses the LLM to analyze the story and repository context, then outputs a deterministic plan.
"""

import json
import uuid
from typing import Dict, Optional, List

from agents.base_agent import BaseAgent, AgentResult
from planning.models import ImplementationPlan, Task, TaskType
from utils.logger import logger


PLANNER_SYSTEM_PROMPT = """You are Ada's Implementation Planner.

Your job is to convert a user story into a structured implementation plan with atomic engineering tasks.

RULES:
1. Each task must be ATOMIC — one focused piece of work (e.g., one migration, one endpoint, one test file).
2. Dependencies must be EXPLICIT — if Task B requires Task A's output, list Task A in dependencies.
3. Tasks must be EXECUTION READY — a coding agent should be able to implement each task independently given the description and success criteria.
4. Order tasks logically: schema/config first, then backend logic, then API, then tests, then frontend.
5. Every task must have clear success_criteria that can be verified programmatically.

TASK TYPES (use exactly one per task):
- database: schema changes, migrations, models
- backend: business logic, services, utilities
- api: endpoints, routes, request/response handling
- frontend: UI components, pages, client-side logic
- test: test files, test infrastructure
- refactor: code restructuring, cleanup
- config: configuration, environment, build changes

OUTPUT FORMAT:
You MUST respond with ONLY valid JSON. No explanation text before or after.

```json
{
  "feature_title": "Short descriptive title",
  "feature_description": "What this feature does and why",
  "success_criteria": ["Global criterion 1", "Global criterion 2"],
  "tasks": [
    {
      "task_id": "task_1",
      "title": "Short task title",
      "description": "Detailed description of what to implement. Include file paths, function signatures, and behavior details.",
      "type": "backend",
      "dependencies": [],
      "success_criteria": ["Specific verifiable criterion"]
    }
  ]
}
```

GUIDELINES:
- Aim for 2-6 tasks per story (keep it focused)
- Task IDs must be sequential: task_1, task_2, task_3, etc.
- Dependencies reference other task_ids from the same plan
- Don't create tasks for git operations (handled externally)
- Include test tasks when the story requires new functionality
- For simple stories, fewer tasks is better
"""


class PlannerAgent(BaseAgent):
    """
    Converts user stories into structured ImplementationPlans.
    
    Unlike the conversational PlanningAgent, this agent takes a complete story
    and analyzes the repository to produce a deterministic execution plan.
    """

    def __init__(self, llm_client, tools=None):
        """
        Args:
            llm_client: LLM client for plan generation.
            tools: Optional tools for repo exploration (not used in planning prompt, 
                   but could be used for repo context gathering).
        """
        super().__init__("ImplementationPlanner", llm_client, tools)

    def plan(self, story: Dict, repo_path: str, context: Optional[Dict] = None) -> Optional[ImplementationPlan]:
        """
        Generate an ImplementationPlan from a user story.

        Args:
            story: User story dict with title, description, acceptance_criteria.
            repo_path: Path to the repository for context.
            context: Optional additional context.

        Returns:
            ImplementationPlan if successful, None on failure.
        """
        context = context or {}
        plan_id = str(uuid.uuid4())

        # Build the planning prompt
        user_prompt = self._build_user_prompt(story, context)

        # Reset and configure LLM
        self.llm.reset_conversation()
        self.llm.conversation_history.append({"role": "system", "content": PLANNER_SYSTEM_PROMPT})

        logger.info(self.name, f"Generating implementation plan for: {story.get('title', 'Unknown')}")

        try:
            response = self.llm.generate(user_prompt, tools=None)
            content = response.get("content", "") or ""

            plan_data = self._extract_plan(content)
            if not plan_data:
                logger.error(self.name, "Failed to extract valid plan from LLM response")
                return None

            # Build the ImplementationPlan
            plan = ImplementationPlan.from_dict({
                "plan_id": plan_id,
                **plan_data,
            })

            logger.info(self.name, f"Plan generated: {len(plan.tasks)} tasks")
            for task in plan.tasks:
                deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
                logger.info(self.name, f"  [{task.task_id}] {task.title}{deps}")

            return plan

        except Exception as e:
            logger.error(self.name, f"Planning failed: {e}")
            return None

    def run(self, task: Dict, repo_path: str, context: Dict) -> AgentResult:
        """
        BaseAgent interface. Delegates to plan().
        """
        plan = self.plan(task, repo_path, context)
        if plan:
            return AgentResult(success=True, output=plan.to_dict())
        return AgentResult(success=False, output="Planning failed")

    def _build_user_prompt(self, story: Dict, context: Dict) -> str:
        """Build the user prompt combining the story and any available context."""
        parts = ["Here is the user story to plan:\n"]

        parts.append(f"Title: {story.get('title', 'N/A')}")
        parts.append(f"Description: {story.get('description', 'N/A')}")

        criteria = story.get("acceptance_criteria", [])
        if criteria:
            parts.append("\nAcceptance Criteria:")
            for i, ac in enumerate(criteria, 1):
                parts.append(f"  {i}. {ac}")

        # Include repo context if available
        repo_summary = context.get("repo_summary")
        if repo_summary:
            parts.append(f"\nRepository Context:\n{repo_summary}")

        parts.append("\nGenerate the implementation plan as JSON.")
        return "\n".join(parts)

    def _extract_plan(self, content: str) -> Optional[Dict]:
        """Extract plan JSON from LLM response."""
        try:
            # Try to find JSON block
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

            data = json.loads(json_str)

            # Validate required structure
            if "tasks" not in data or not isinstance(data["tasks"], list):
                logger.warning(self.name, "Plan missing 'tasks' list")
                return None

            if not data.get("feature_title"):
                logger.warning(self.name, "Plan missing 'feature_title'")
                return None

            # Validate each task has required fields
            for task in data["tasks"]:
                required = ["task_id", "title", "description", "type"]
                missing = [f for f in required if f not in task]
                if missing:
                    logger.warning(self.name, f"Task missing fields: {missing}")
                    return None

            return data

        except json.JSONDecodeError as e:
            logger.warning(self.name, f"Failed to parse plan JSON: {e}")
            return None
