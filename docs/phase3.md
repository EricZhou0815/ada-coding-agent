Below is a **concise but complete design document**  to implement the **Phase-3 architecture on top of `ada-coding-agent`**.
It focuses on **deterministic planning + execution orchestration**, which aligns with the **Plan → TaskGraph → Execution** model we discussed.

---

# ADA Coding Agent

## Phase 3 Design Document

### Deterministic Planning & Execution Architecture

Version: `v0.3`
Status: **Implementation Ready**

---

# 1. Purpose

The purpose of this design is to evolve **ada-coding-agent** into a **deterministic autonomous coding system** that:

1. Converts a **user story** into a structured **Implementation Plan**
2. Breaks the plan into **atomic engineering tasks**
3. Executes tasks through **coding agents**
4. Verifies completion through **deterministic validation**

This architecture ensures:

* reliability
* traceability
* parallel execution
* reduced hallucination
* scalable automation

---

# 2. System Goals

The system must:

### Functional Goals

* Convert user stories → implementation plans
* generate structured tasks
* manage task dependencies
* execute coding tasks
* verify code changes
* determine feature completion

### Non-Functional Goals

* deterministic execution
* task traceability
* reproducible runs
* scalable orchestration
* clear system state

---

# 3. High Level Architecture

System flow:

```
User Story
    │
    ▼
Planning Agent
    │
    ▼
ImplementationPlan
    │
    ▼
TaskGraph Builder
    │
    ▼
Task Scheduler
    │
    ▼
Run Execution
    │
    ▼
Coding Agent
    │
    ▼
Verification
    │
    ▼
Task Completion
```

Core components:

```
planning/
orchestration/
execution/
agents/
verification/
intelligence/
```

---

# 4. Core Data Models

All agents operate on **structured models** rather than raw prompts.

---

# 4.1 ImplementationPlan

Represents the high level plan for implementing a feature.

```json
{
  "plan_id": "plan_uuid",
  "feature_title": "Password Reset Feature",
  "feature_description": "Allow users to reset their password via email verification.",
  "tasks": ["task_1","task_2","task_3"],
  "success_criteria": [
    "all tests pass",
    "endpoint works",
    "email is sent"
  ],
  "created_at": "timestamp"
}
```

Responsibilities:

* describe feature implementation
* reference tasks
* define feature success criteria

---

# 4.2 Task

Atomic unit of engineering work.

Each task should ideally correspond to **one commit or pull request**.

Example:

```json
{
  "task_id": "task_1",
  "plan_id": "plan_uuid",
  "title": "Add reset_token column to users table",
  "description": "Update database schema to support password reset token.",
  "type": "database",
  "dependencies": [],
  "status": "pending",
  "success_criteria": [
    "migration file created",
    "tests pass"
  ]
}
```

Task Types:

```
database
backend
frontend
api
test
refactor
config
```

Task Status:

```
pending
running
completed
failed
```

---

# 4.3 TaskGraph

Represents task dependency relationships.

Example:

```
Task1: DB migration
    ↓
Task2: API endpoint
    ↓
Task3: Unit tests
```

Data model:

```json
{
  "graph_id": "graph_uuid",
  "plan_id": "plan_uuid",
  "tasks": {
    "task_1": { "dependencies": [] },
    "task_2": { "dependencies": ["task_1"] },
    "task_3": { "dependencies": ["task_2"] }
  }
}
```

TaskGraph must be a **Directed Acyclic Graph (DAG)**.

---

# 4.4 RunExecution

Represents a **single coding agent execution**.

Example:

```json
{
  "run_id": "run_uuid",
  "task_id": "task_1",
  "status": "running",
  "workspace_path": "/runs/run_uuid/",
  "branch": "feature/password-reset",
  "retry_count": 0,
  "logs": [],
  "result": null
}
```

Run states:

```
pending
running
success
failed
retrying
```

---

# 4.5 VerificationResult

Represents task validation outcome.

```json
{
  "task_id": "task_1",
  "tests_passed": true,
  "lint_passed": true,
  "build_passed": true,
  "validation_passed": true
}
```

A task is **completed only if validation_passed = true**.

---

# 5. Planning Agent

The Planning Agent converts **user stories → structured implementation plans**.

Inputs:

```
User story
Repository summary
Repo knowledge graph (optional)
```

Output:

```
ImplementationPlan
Task list
Task dependencies
```

Planner output schema:

```json
{
  "plan": {
    "feature_title": "",
    "feature_description": ""
  },
  "tasks": [
    {
      "task_id": "",
      "title": "",
      "description": "",
      "type": "",
      "dependencies": []
    }
  ]
}
```

Planner rules:

* tasks must be **atomic**
* dependencies must be **explicit**
* tasks should be **execution ready**

---

# 6. Task Scheduler

The scheduler selects tasks whose dependencies are satisfied.

Algorithm:

```
for task in task_graph:
    if dependencies_completed(task):
        schedule_run(task)
```

Parallel execution is allowed if:

```
dependencies_completed(task) == true
```

---

# 7. Execution Engine

Responsible for running coding agents.

Steps:

```
create workspace
checkout branch
generate prompt
run coding agent
commit changes
run verification
update task state
```

Workspace layout:

```
runs/
   run_123/
        repo/
        logs/
        outputs/
```

---

# 8. Coding Agent

The coding agent receives:

```
task description
repo context
relevant files
success criteria
```

Expected output:

```
code changes
tests
commit message
```

Prompt structure:

```
SYSTEM:
You are an expert software engineer.

TASK:
<task description>

SUCCESS CRITERIA:
<criteria>

REPOSITORY CONTEXT:
<files summary>

OUTPUT:
Implement the changes required.
```

---

# 9. Verification System

Verification ensures code correctness.

Validation pipeline:

```
lint
build
tests
```

Example pipeline:

```
npm run lint
npm run build
npm run test
```

VerificationResult determines task completion.

---

# 10. Feature Completion Logic

Feature is complete when:

```
all tasks.status == completed
AND
all verification passed
```

Feature status states:

```
pending
in_progress
completed
failed
```

---

# 11. Repository Knowledge Graph (Optional)

Represents repository structure.

Example nodes:

```
file
class
function
endpoint
database_table
test
```

Example edges:

```
imports
calls
depends_on
extends
```

Benefits:

```
better planning
architecture awareness
reduced hallucination
```

---

# 12. Suggested Repository Structure

```
ada-coding-agent/

planning/
    planner_agent.py
    implementation_plan.py

orchestration/
    task_graph.py
    task_scheduler.py

execution/
    run_execution.py
    workspace_manager.py

agents/
    coding_agent.py
    review_agent.py

verification/
    test_runner.py
    quality_gate.py

intelligence/
    repo_graph_builder.py
    dependency_analyzer.py
```

---

# 13. Logging & Observability

System must record:

```
planning output
task transitions
run logs
verification results
```

Logs stored in:

```
runs/<run_id>/logs
```

---

# 14. Failure Handling

Failures can occur at:

```
planning
execution
verification
```

Retry policy:

```
max_retries = 3
```

On failure:

```
retry task
or escalate to human
```

---

# 15. Future Extensions

Phase 4 improvements:

```
multi-agent collaboration
automatic code review agents
repo knowledge graph
long running feature memory
parallel feature development
```

---

# 16. Success Metrics

The system is successful if it can:

```
convert story → PR automatically
execute tasks reliably
detect completion automatically
scale across features
```

---

# 17. MVP Scope (Phase 3)

Required components:

```
Planning Agent
TaskGraph
Task Scheduler
Execution Engine
Coding Agent
Verification
```

Not required yet:

```
multi-agent collaboration
repo knowledge graph
self-improving planners
```

---

# Final Architecture Summary

```
User Story
     │
     ▼
Planning Agent
     │
     ▼
ImplementationPlan
     │
     ▼
TaskGraph
     │
     ▼
Task Scheduler
     │
     ▼
Run Execution
     │
     ▼
Coding Agent
     │
     ▼
Verification
     │
     ▼
Feature Completed
```
