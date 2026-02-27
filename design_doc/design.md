# Ada: Autonomous LLM Coding Agent – Design Document

This document summarizes the **design principles, architecture, and decisions** for Ada, the autonomous AI software engineer. It is intended as a guideline for future AI coding agents, contributors, or developers.

---

## **1. Project Philosophy**

1. **Human-like AI Persona**  
   - Ada is treated as a **human engineer**: autonomous, reasoning, and capable of planning.
   - Prompts and instructions are written in a way that simulates human decision-making, rather than rigid step instructions.

2. **Autonomy Over Hard-Coded Steps**  
   - Internal loops, task breakdown, and execution decisions are **fully handled by the LLM**.
   - Python orchestrator only provides isolation, execution limits, and sequential task order.

3. **Future-Proof Design**  
   - Ada is designed to leverage **LLM capability improvements** without changing the core framework.
   - No logic should limit the agent’s potential to plan, reason, or code more efficiently as LLMs improve.

---

## **2. Architecture Overview**

- **Tasks:** Atomic tasks (JSON) define the work to be done.  
- **Orchestrator:** Runs each task in Docker isolation, sequentially.  
- **Ada Agent:** LLM-powered coding agent with tools interface.  
  - **Coding Agent:** Executes tasks autonomously.  
  - **Validation Agent:** Checks code quality and rule compliance.  
- **Tools:** Exposed sandbox functions (read/write/list/run/apply_patch).  
- **Repo Snapshot:** Mountable repo for safe isolated execution.

---

## **3. Core Modules & Responsibilities**

### 3.1 Coding Agent
- Receives one atomic task at a time.
- Decides internally how to modify code.
- Uses provided tools for filesystem and execution.
- Handles **planning, coding, and self-verification**.
- Output is structured in JSON, declaring `"finish"` when done.

### 3.2 Validation Agent
- Validates code using **linting, tests, and custom rules**.
- Returns feedback to coding agent for iterative improvement.
- Ensures **atomic task completion criteria** are met.

### 3.3 Tools Interface
- Sandbox functions to allow code modifications:
  - `read_file(path)`, `write_file(path, content)`, `delete_file(path)`, `list_files(directory)`
  - `run_command(command)` – shell execution in isolated environment
  - `apply_patch(patch_text)` – optional Git patch application
- Enables **autonomy while restricting direct system control**.

### 3.4 Orchestrator
- Launches each atomic task in **Docker containers** for isolation.
- Enforces **sequential task order**.
- Limits **max iterations** per task to avoid infinite loops.
- Manages **task dependencies** (future extension).

---

## **4. Design Principles**

1. **Autonomy:** Agent controls the task execution loop.  
2. **Isolation:** Each task runs in a Docker container, sandboxed from the host and other tasks.  
3. **Sequential Execution:** For MVP, tasks are executed in order; dependency logic is preserved.  
4. **Feedback Loops:** Validation results are sent back to Ada for refinement.  
5. **Extensibility:** New tools, validation rules, or LLM models can be added without changing orchestration.  
6. **Future-Proof:** As LLMs improve, Ada can make smarter decisions without modifying orchestration code.  

---

## **5. Task Execution Flow**

1. Orchestrator receives an atomic task.
2. Launches **Docker container** with repo snapshot mounted.
3. Ada reads the task and previous completed tasks.
4. Ada decides how to execute using the tools interface.
5. Validation agent checks code changes.
6. If validation fails:
   - Feedback is returned to Ada.
   - Ada iterates (max iteration limit enforced).
7. If validation passes:
   - Task marked complete.
   - Orchestrator proceeds to next atomic task.

---

## **6. Naming & Persona Guidelines**

- All agents, tools, and logs refer to the human-like persona **“Ada”**.
- Prompts and outputs should maintain **human engineer style**:
  - “I will implement X…”  
  - “Here’s how I plan to modify the code…”  
- Persona helps maintain **consistent behavior** across tasks and agents.

---

## **7. Guidelines for AI Coding Agents**

1. Always treat the **task as atomic and sequential** unless orchestrator specifies parallel execution.  
2. Use the **tools interface exclusively** to manipulate code and environment.  
3. Only declare task completion when **all acceptance criteria are satisfied**.  
4. Maintain internal reasoning loops inside the LLM; **Python orchestrator does not define task steps**.  
5. Preserve human persona, logs, and structured output for clarity.  
6. Ensure **max iteration limits** to avoid infinite loops.

---

## **8. Future Enhancements**

- Parallel task execution with dependency resolution.  
- Full LLM integration with code suggestion, review, and commit.  
- Advanced validation: CI/CD style linting, unit tests, type checks.  
- Task prioritization and scheduling.  
- Knowledge graph to track tasks, decisions, and repo history.

---

## **9. Summary**

Ada provides a **humanized, autonomous, and future-proof LLM coding framework**.  
This design ensures:

- Sequential atomic task execution  
- Safe sandboxed execution  
- Autonomy and feedback loops  
- Easy integration with stronger LLMs in the future  

This document should guide **any AI agent** joining Ada in continuing or extending the project.
