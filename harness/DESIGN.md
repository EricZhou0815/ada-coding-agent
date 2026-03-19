# Architecture & Design (`DESIGN.md`)

This document outlines the engineering architecture of the Ada autonomous coding agent project. AI assistants operating within this codebase should use these guidelines to understand system interactions and constraints.

## System Overview
Ada is designed as a distributed, multi-agent LLM-powered application intended to complete entire software development lifecycles (SDLC) from reading a user story to opening a Pull Request.

### Key Components

1. **API Gateway & Job Intake (`api/`)**
   - Built with FastAPI.
   - Handles story intake, REST endpoints, UI polling/streaming, and API key authentication.
   - Subscribes to Redis Pub/Sub for real-time log streaming to the Next.js UI via Server-Sent Events (SSE).

2. **Asynchronous Worker Fleet (`worker/`)**
   - Driven by Celery and Redis.
   - Each worker processes an independent story.
   - Designed for horizontal scaling to handle parallel backlog execution.

3. **Repository Intelligence Layer (`intelligence/`)**
   - Resolves necessary context for agent coding via AST parsing (Tree-sitter).
   - Generates a Knowledge Graph of classes, functions, imports, and dependencies.
   - The `ContextRetriever` matches tasks to specific symbols, giving the coding agent precise context rather than blind repository scans.

4. **Deterministic Planning (`planning/`, `orchestration/`)**
   - Decomposes a User Story into a DAG of atomic `Task` objects.
   - Executed through a `TaskScheduler` with topological sorting and per-task retries.

5. **Agent Hierarchy (`agents/`)**
   - **CodingAgent**: The core executor making targeted code edits.
   - **PlanningAgent**: Interactive requirement clarification before coding.
   - **ValidationAgent**: Assesses implementation against the initial acceptance criteria.

6. **Isolation Engine (`isolation/`)**
   - Critical for safely running untrusted LLM-generated code.
   - Backends: `Sandbox` (local folder), `DockerBackend` (container-based), `ECSBackend` (AWS hardware isolation).

## Core Design Principles
- **No Side Effects in Global State**: Tasks execute in isolated environments. The codebase should strictly decouple the planning engine from the isolated execution engine.
- **Failover & Resilience**: Since LLM APIs can be flaky, rate limits, API key rotation, and task-level retries must be inherently supported (implemented in `llm/` and execution loops).
- **Asynchronous by Default**: For long-running operations (ast scanning, complex planning, docker container execution), avoid blocking the API server.
