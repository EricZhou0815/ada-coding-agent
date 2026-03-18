# Planning & Roadmaps (`PLANS.md`)

This document is instructions to AI agents working on Ada: how tasks are managed, structured, and implemented within the Ada codebase.

## Internal Engineering Planning
Ada's evolution is divided into specific phases. When a user asks you to implement a new feature (e.g., adding an endpoint or a new tool), refer to these phases to maintain consistency.

### Feature Decomposition
1. **Repository Intelligence (Phase 4)**: 
   - Before executing code, tasks use the `ContextRetriever` to pull task-specific definitions from AST parses.
   - Any new tool or agent module must assume a `task_context` is provided and avoid blind repository searches when possible.
2. **Deterministic Pipelines (Phase 3)**:
   - Ada decomposes user stories into a DAG (Directed Acyclic Graph) of tasks. 
   - Do not shortcut execution loops. If adding new business logic to run a script, it should fit within the `TaskScheduler` execution loop. Tasks should be atomic and executable within isolated boundaries.
3. **Pluggable Architecture**:
   - VCS backends (`github_client.py`, `gitlab_client.py`) and execution backends (`sandbox.py`, `docker_backend.py`, `ecs_backend.py`) must be loosely coupled from core orchestration. Add new features via interfaces, not hardcoded monolithic changes.

## Developing New Features
1. **Write the Plan First**: We follow a Plan-before-Code discipline.
2. **Scope the Implementation**: New APIs go to `api/`, new business logic goes to `orchestrator/`, new graph logic to `intelligence/`.
3. **Persist the State**: Ensure robust SQLite/PostgreSQL integrations for new state definitions. All models belong in their respective `models.py` files.
4. **Log Everything**: The Next.js frontend relies on SSE streams. Use `logger.send_to_ui()` explicitly when interacting with UI-facing workflows.
