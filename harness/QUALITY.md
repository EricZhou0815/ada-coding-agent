# Engineering Quality & Coding Standards (`QUALITY.md`)

This document defines the strict quality guidelines for Ada's Python codebase. AI agents contributing to this project must ensure code fulfills these expectations.

## Python Standards
- **Typing (`typing` module)**: Strongly type every function signature, variable, and return value. Run MyPy or Pydantic statically whenever possible. Use `Optional`, `Dict`, `List`, `Any` correctly.
- **Pydantic Models**: For data transfer and agent schemas, Pydantic should be used inherently (used heavily in `planning.models`, `api.main`, etc.). Ensure proper `Field` validations and examples where necessary.
- **Error Handling**: Do not write blanket `except Exception as e: pass` statements. If swallowing an error is necessary, add a verbose comment and log via the application logger.

## Reliability
- **Retry Mechanisms**: All LLM calls and network operations (VCS operations like cloning or pushing) must have automated retries. Use appropriate wait/back-off loops.
- **Resource Management**: Processes running inside isolated backends (like Docker) must clean up their own dangling images/containers/files on completion or error.
- **Idempotency**: Execution scripts and database initialization operations should be runnable multiple times without side effects or fatal errors.

## Code formatting
- Stick to standard PEP-8 conventions. Use `black` and `isort` stylings as a mental rule if manual auto-formatting is not available.
- Keep module limits focused. Do not bloated single `.py` files over 500-1000 lines if components can be logically divided (e.g., separating specific endpoints into different routers, tools into different categories).

## Testing Practices
- **Deterministic Quality Gates**: The `QualityGate` executes lints, builds, and tests locally. Agent contributions must pass existing tests in `/tests`.
- **Integration Tests**: Critical pathways (API -> Orchestrator -> Execution -> Git) require solid e2e/integration scripts (e.g., `smoke_test_system.py`) to verify regressions before finalizing changes.
- **No Mock-heavy Anti-patterns**: Where feasible, tests should run against an ephemeral database (SQLite memory) and genuine isolation loops.

## LLM API Conventions
- Implement automated fallback logic across model sizes when hitting rate limits (429) or token limits. Handle key rotation correctly when `GROQ_API_KEYS` or corresponding keys are exhausted.
- Keep system prompts in separate constants or modules. Prevent bloated f-strings scattered randomly throughout business logic.
