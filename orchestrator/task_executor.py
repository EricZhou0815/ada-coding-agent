from typing import Dict, List

class AtomicTaskExecutor:
    """
    Orchestrates the execution of a single atomic task by coordinating the CodingAgent 
    and the ValidationAgent in a feedback loop.
    """

    def __init__(self, coding_agent, validation_agent, repo_path: str, max_iterations: int = 25):
        """
        Initializes the Task Executor.

        Args:
            coding_agent (CodingAgent): The AI agent responsible for solving the task.
            validation_agent (ValidationAgent): The agent responsible for verifying code changes.
            repo_path (str): The filesystem path to the isolated sandbox or target repository.
            max_iterations (int, optional): The maximum number of retry loops allowed if validation fails. Defaults to 25.
        """
        self.coding_agent = coding_agent
        self.validation_agent = validation_agent
        self.repo_path = repo_path
        self.max_iterations = max_iterations

    def execute_task(self, atomic_task: Dict, completed_tasks: List[str]) -> bool:
        """
        Runs the full execution block for a single task until validation passes or iterations run out.

        Args:
            atomic_task (Dict): The task specifications (title, description, criteria).
            completed_tasks (List[str]): Context array of previously finished tasks.

        Returns:
            bool: True if the task successfully passed validation.

        Raises:
            RuntimeError: If the task exceeds the maximum number of retry iterations.
        """
        iteration_count = 0
        validation_feedback = []

        while True:
            iteration_count += 1
            if iteration_count > self.max_iterations:
                raise RuntimeError(
                    f"Ada's task {atomic_task['task_id']} exceeded max iterations ({self.max_iterations})"
                )

            # Run Ada coding agent
            self.coding_agent.run(
                atomic_task=atomic_task,
                repo_path=self.repo_path,
                completed_tasks=completed_tasks,
                validation_feedback=validation_feedback
            )

            # Validate repo after Ada's execution
            validation_result = self.validation_agent.validate(self.repo_path)

            if validation_result["passed"]:
                print(f"Ada completed task {atomic_task['task_id']} successfully.")
                return True

            # Feedback loop to Ada
            validation_feedback = validation_result["feedback"]
            print(f"Validation failed for task {atomic_task['task_id']}, sending feedback to Ada.")