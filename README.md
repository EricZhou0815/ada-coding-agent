# Ada - Autonomous AI Software Engineering Team

Ada is a multi-agent AI system that integrates directly into the software development lifecycle. By treating the agent as a longitudinal autonomous engineer, Ada processes full User Stories end-to-end: exploring code, planning implementation, writing changes, and opening Pull Requests — all without human intervention.

---

## 🚀 Features

- **Repository Intelligence Layer (Phase 4)**: Tree-sitter AST parsing builds a knowledge graph of every class, function, import, and dependency in your codebase. Before planning or coding, Ada retrieves task-specific context — relevant files, symbols, and dependency chains — so agents make precision edits instead of blind modifications.
- **Deterministic Planning Pipeline (Phase 3)**: User stories are decomposed into structured `ImplementationPlan`s with atomic tasks, explicit dependencies, and a DAG-based task scheduler. Each task runs through an isolated CodingAgent → QualityGate verification loop with automatic retries.
- **Planning Agent**: Interactive requirement clarification before coding. Transform unclear requests into complete user stories through LLM-driven conversation focused on behavioral requirements. See [Planning Agent Guide](docs/PLANNING_AGENT.md).
- **Senior Autonomous Logic**: Ada behaves as a senior engineer — exploring code, creating internal monologues, and following a strict Plan-before-Code discipline.
- **Full SDLC Integration**: Provide a repository URL and a backlog. Ada clones, branches, codes, commits, and opens PRs automatically.
- **Multi-Platform VCS Support**: Modular VCS architecture with GitHub and GitLab implementations. Easily switch platforms via `VCS_PLATFORM` environment variable.
- **Pluggable Isolation (Prod-Ready)**: Support for multiple execution backends:
    - **Sandbox**: Lightweight local folder isolation.
    - **Docker**: Container-level isolation per story.
    - **AWS ECS (Fargate)**: True hardware-level isolation for untrusted code execution.
- **Production-Grade Persistence**: Moves from SQLite to **PostgreSQL** for reliable, concurrent data management in distributed environments.
- **High Autonomy (80+ Tool Calls)**: Ada is equipped with a large tool-call budget, allowing for massive refactors and multi-file changes in one session.
- **Parallel Backlog Execution**: Distribute multiple User Stories across a cluster of workers. Ada can process an entire backlog in parallel, horizontally scaling to meet your team's velocity.
- **Template-Driven PRs**: Generates structured PRs using `.ada/pr_template.md`, including completed tasks and file diff summaries.
- **VCS Webhook Support**: Modular webhook architecture supporting GitHub and GitLab for automated feedback loops.
- **Closed-Loop Development**:
    - **CI/CD Auto-Fix**: Ada listens to VCS Webhooks. If a CI pipeline fails, she automatically downloads log artifacts, reproduces the bug, and pushes a patch.
    - **Human Feedback**: Comment on an Ada PR, and she will autonomously apply your requested changes and push the update.
- **Real-time Engineering Audit**: Follow Ada's reasoning in the Console UI with live streaming of tool calls, outputs, and internal "monologues".
- **LLM Support**: Built-in support for **Groq** (extremely fast), **DeepSeek** (affordable + powerful), and **OpenAI**.
- **API Key Rotation**: Automatic failover across multiple API keys on rate limits or quota exhaustion — essential for high-volume production workloads.
- **API Authentication**: Secure `/api/v1/execute` endpoint with configurable API keys to prevent unauthorized job submissions and cost abuse.

---

## 🏛 Architecture

### System Flow (Distributed Architecture)
```
┌──────────────────────────┐      ┌──────────────────────────┐
│   Next.js Console UI     │      │   GitHub Webhooks        │
│   (Interaction & Logs)   │      │   (CI Fails / Comments)  │
└───────────┬──────────────┘      └───────────┬──────────────┘
            │                                 │
            ▼                                 ▼
┌────────────────────────────────────────────────────────────┐
│                  FastAPI Gateway (api/)                    │
│    (Auth, Story Intake, Job Management, Log Streaming)     │
└───────────┬─────────────────────────────────┬──────────────┘
            │                                 │
            │   [1] Dispatch Story            │   [4] Persist Logs/State
            ▼                                 ▼
┌──────────────────────────┐      ┌──────────────────────────┐
│   Redis Message Broker   │      │   PostgreSQL Database    │
│   (Celery Task Queue)    │      │    (Job Store & Logs)    │
└───────────┬──────────────┘      └───────────▲──────────────┘
            │                                 │
            │   [2] Consume Task              │   [3] Progress Updates
            ▼                                 │
┌─────────────────────────────────────────────┴──────────────┐
│              Autonomous Workers (worker/)                  │
│    (Horizontal Scaling • One Story per Worker)             │
└───────────┬───────────────────┬────────────────────────────┘
            │                   │
            │ [5] Plan & Execute│ [6] Stream Logs (Pub/Sub)
            ▼                   ▼
┌──────────────────────────────────────────────────────────┐
│              Planning & Intelligence Pipeline            │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Phase 4: Repository Intelligence Layer            │ │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────────────┐ │ │
│  │  │  Repo    │▶│  AST     │▶│  Knowledge Graph    │ │ │
│  │  │  Scanner │ │  Parser  │ │  (nodes + edges)    │ │ │
│  │  └──────────┘ └──────────┘ └────────┬────────────┘ │ │
│  │                                     │              │ │
│  │                            ┌────────▼────────────┐ │ │
│  │                            │  Context Retriever  │ │ │
│  │                            │  (task → top-k)     │ │ │
│  │                            └────────┬────────────┘ │ │
│  └─────────────────────────────────────┼──────────────┘ │
│                                        │ context        │
│  ┌─────────────┐    ┌─────────────┐    ▼ ┌───────────┐  │
│  │  Planner    │───▶│  TaskGraph  │───▶│ Scheduler  │  │
│  │  Agent      │    │  (DAG)      │    │ (topo-sort)│  │
│  └─────────────┘    └─────────────┘    └─────┬──────┘  │
│                                              │         │
│                         ┌────────────────────┘         │
│                         ▼                              │
│  ┌─────────────────────────────────────────────────────┐│
│  │  Per-Task Execution Loop (with retries)             ││
│  │  ┌────────────┐  ┌────────────┐  ┌───────────────┐ ││
│  │  │ Isolation  │─▶│  Coding    │─▶│  Quality Gate │ ││
│  │  │ (Sandbox)  │  │  Agent     │  │  (lint/test)  │ ││
│  │  └────────────┘  └────────────┘  └───────────────┘ ││
│  └─────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────┐    ┌──────────────────────┐
│ Results copied back  │    │   Redis (logs:id)    │
│ to feature branch    │    │   (SSE to Browser)   │
└──────────────────────┘    └──────────────────────┘
```

> **Note on Log Streaming**: While stories are queued via **Celery**, logs bypass the task queue and use **Redis Pub/Sub** for real-time streaming. The API subscribes to these logs and pushes them to the UI via Server-Sent Events (SSE), ensuring zero-latency monitoring.

### Execution Pipeline (The Story Lifecycle)
1. **Bootstrap**: `SDLCOrchestrator` clones the repo and creates a feature branch.
2. **Intelligence** *(Phase 4)*: `RepoGraphBuilder` scans the repo, parses ASTs with Tree-sitter, and builds a knowledge graph of files, classes, functions, imports, and dependencies.
3. **Planning** *(Phase 3)*: `PlannerAgent` receives the graph summary and decomposes the story into an `ImplementationPlan` with atomic `Task` objects and explicit dependency edges.
4. **Task Scheduling**: `TaskGraph` validates the DAG (cycle detection), and `TaskScheduler` dispatches tasks in topological order with per-task retries.
5. **Context Retrieval** *(Phase 4)*: `ContextRetriever` extracts keywords from each task, matches against the knowledge graph, traverses dependency edges, and returns the most relevant files and symbols.
6. **Isolation**: Re-configurable backends (Sandbox, Docker, or ECS) ensure zero-side effects per task.
7. **Reasoning**: `CodingAgent` (Ada) receives task-specific context and makes precision edits instead of blind modifications.
8. **Verification**: `QualityGate` runs deterministic lint/build/test commands; `ValidationAgent` ensures acceptance criteria are met.
9. **Finalization**: `GitManager` commits changes, pushes to origin, and the VCS client opens the PR.

> **Legacy mode**: Set `use_planning=False` on `SDLCOrchestrator` to bypass Phase 3 planning and use the direct `EpicOrchestrator` pipeline.

---

## 🛠 Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **💡 Database**: Ada uses **SQLite by default** (auto-created, zero config). Only install PostgreSQL if you need multi-instance production deployments. See [Local Setup Guide](SETUP_WITHOUT_DOCKER.md) for details.

### 2. Configure environment variables

```bash
cp env.example .env
```

#### LLM Keys (Groq recommended)
```bash
# Single key (simple setup)
GROQ_API_KEY=gsk_your_key_here

# Multiple keys for automatic failover (recommended for production)
# Ada automatically rotates to the next key on rate limits or quota exhaustion
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3

# DeepSeek (affordable, powerful alternative)
DEEPSEEK_API_KEY=sk_your_key_here
# Or multiple keys:
# DEEPSEEK_API_KEYS=sk_key1,sk_key2,sk_key3

# OpenAI (optional fallback)
OPENAI_API_KEY=sk_your_key_here
# Or multiple keys:
# OPENAI_API_KEYS=sk_key1,sk_key2,sk_key3
```

> **💡 Multi-Key Rotation**: When using `GROQ_API_KEYS`, `DEEPSEEK_API_KEYS`, or `OPENAI_API_KEYS` (comma-separated), Ada automatically handles:
> - **Rate limits (429)**: Rotates to next key with 60s cooldown
> - **Quota exhaustion**: Rotates to next key with 1hr cooldown  
> - **Invalid keys (401)**: Marks key as permanently failed, uses remaining keys

#### VCS Platform (GitHub or GitLab)
```bash
# Default: github
VCS_PLATFORM=github

# GitHub token for PR creation
GITHUB_TOKEN=ghp_your_pat_here

# For GitLab (set VCS_PLATFORM=gitlab first):
# GITLAB_TOKEN=glpat_your_token_here
# GITLAB_URL=https://gitlab.com  # or your self-hosted instance
```

#### API Authentication (Required for Production)
```bash
# API keys for authenticating requests to /api/v1/execute endpoint
# CRITICAL: Set this before deploying to prevent unauthorized job submissions
# Format: Comma-separated list of keys (no spaces)
API_KEYS=ada-prod-key-abc123,ada-ui-key-xyz789

# Generate secure keys with:
# openssl rand -hex 32
```

> **🔒 Security**: Without `API_KEYS` configured, anyone with your API URL can submit unlimited jobs.  
> **Dev Mode**: If `API_KEYS` is not set, authentication is disabled with a warning (local development only).

#### Ada Management Scope (Control which PRs Ada handles)
```bash
# Branch prefix for Ada-managed branches (default: ada-ai/)
# Ada creates branches like: ada-ai/STORY-123-feature-name
ADA_BRANCH_PREFIX=ada-ai/

# Allow Ada to respond to @ada-ai on ALL PRs (default: false)
# If false, @ada-ai only works on Ada's own branches
# If true, team members can use @ada-ai on human-created PRs
ADA_HANDLE_ALL_PRS=false

# Auto-fix CI failures on ALL branches (default: false)
# If false, only auto-fixes CI on Ada's branches (recommended)
ADA_AUTO_FIX_CI_ALL=false
```

> **🔒 Safe Defaults**: By default, Ada only manages branches/PRs she creates (prefix: `ada-ai/`).  
> Set `ADA_HANDLE_ALL_PRS=true` to let your team use `@ada-ai` comments on any PR.

#### Isolation Backend (Optional)
```bash
ADA_ISOLATION_BACKEND=sandbox  # sandbox, docker, ecs
```

#### AWS ECS Configuration (Only if using ecs backend)
```bash
AWS_REGION=us-east-1
ECS_CLUSTER=ada-cluster
ECS_TASK_DEFINITION=ada-worker-task
ECS_SUBNETS=subnet-12345,subnet-67890
ECS_SECURITY_GROUPS=sg-0abcdef
```

#### Advanced Configuration (Optional)
```bash
# Redis (defaults to localhost if not set)
REDIS_URL=redis://redis:6379/0

# Database (defaults to SQLite if not set)
# Only set this if you want to use PostgreSQL:
# DATABASE_URL=postgresql://ada_user:ada_password@db:5432/ada_db

# Working directory for isolation backends
ADA_TMP_DIR=/tmp/ada_runs
```

### 3. Build & Run

#### Option A: Docker Compose (Recommended for Production)
The easiest way to run the full Ada factory (API + Redis + Postgres + Workers):
```bash
docker-compose up --build
```
*Live docs: [http://localhost:8000/docs](http://localhost:8000/docs)*

#### Option B: Local Setup (No Docker Required)
Perfect for development or if Docker isn't available. Uses SQLite instead of PostgreSQL.

**Prerequisites:**
- Python 3.11+
- Redis (portable download for Windows at `C:\Redis` - no installation needed, see step 3 below)
- Node.js 20+ (for UI only)

**Quick Start:**
```bash
# 1. Install Python dependencies
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Initialize SQLite database
python -c "from api.database import init_db; init_db()"

# 3. Get Redis (Windows - portable, no install required)
# Download: https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip
# Extract to C:\Redis
# Or use PowerShell to download automatically:
# mkdir C:\Redis -Force; Invoke-WebRequest -Uri "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip" -OutFile "$env:TEMP\redis.zip"; Expand-Archive -Path "$env:TEMP\redis.zip" -DestinationPath "C:\Redis" -Force

# 4. Start Redis (keep this terminal open)
# Windows: C:\Redis\redis-server.exe
# Linux/Mac: redis-server

# 5. Run Ada components (3 separate terminals, all with venv activated):

# Terminal 1: Redis (keep running)
C:\Redis\redis-server.exe  # Windows
# redis-server                # Linux/Mac

# Terminal 2: API Server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Celery Worker
export PYTHONPATH=$PWD  # Or: $env:PYTHONPATH = (Get-Location).Path on Windows
celery -A worker.tasks worker --loglevel=info --pool=solo  # Windows requires --pool=solo

# Terminal 4: UI (optional)
cd ui && npm install && npm run dev
```

**What you get:**
- ✅ **SQLite database** (auto-created as `ada_jobs.db` - zero config!)
- ✅ **API server** at http://localhost:8000
- ✅ **API docs** at http://localhost:8000/docs
- ✅ **Console UI** at http://localhost:3000

**Managing Redis:**
```powershell
# Check if Redis is running
C:\Redis\redis-cli.exe ping  # Should return: PONG

# Stop Redis
Stop-Process -Name "redis-server" -Force  # Windows

# Run Redis in background (no console window)
Start-Process -FilePath "C:\Redis\redis-server.exe" -WorkingDirectory "C:\Redis"
```

📖 **[Complete Local Setup Guide](SETUP_WITHOUT_DOCKER.md)** - Detailed instructions for Windows, troubleshooting, and production tips.

**One-Command Startup:**
```bash
# Bash (Git Bash/WSL/Linux/Mac)
./start-local.sh

# PowerShell (Windows)
.\start-local.ps1

# Stop all services
./stop-local.sh  # Bash
.\stop-local.ps1  # PowerShell
```
These scripts automatically start Redis, API, Worker, and UI in the correct order.

#### Option C: Standalone Scripts (No API/Worker needed)
For simple single-story execution without the full stack:

```bash
# Run against local repo
python run_local.py stories/example_story.json ./my_repo

# Run against remote repo (creates PR)
python run_sdlc.py --repo https://github.com/owner/repo --stories stories/backlog.json

# Interactive planning mode
python run_demo.py
```

### 4. Run the Console UI
```bash
cd ui
npm install
npm run dev
```
*Live console: [http://localhost:3000](http://localhost:3000)*

---

## 🚀 Scaling the Factory

Ada is built to handle massive backlogs by horizontally scaling our distributed worker fleet.

### 🏭 Horizontal Scaling (More Workers)
To process multiple User Stories in parallel across different containers:
```bash
# Start the factory with 5 parallel workers
docker-compose up -d --scale worker=5
```
*Each worker picks up stories independently from the Redis queue.*

### ⚡ Tuning Concurrency (Per Worker)
You can adjust how many stories a *single* worker container processes by modifying the `command` in `docker-compose.yml`:
```yaml
# inside docker-compose.yml
command: ["celery", "-A", "worker.tasks", "worker", "--concurrency=4"]
```
*Higher concurrency requires more CPU and RAM per container.*

---

## 🗄️ Database & Persistence

Ada supports two database backends:

### SQLite (Default)
- **Perfect for**: Development, single-instance deployments, getting started
- **Setup**: Zero configuration - database file (`ada_jobs.db`) auto-created on first run
- **Location**: Project root directory
- **When to use**: Local development, demos, or small-scale production (single API instance)

### PostgreSQL (Production)
- **Perfect for**: Multi-instance deployments, high concurrency, horizontal scaling
- **Setup**: Configure `DATABASE_URL` in `.env` (see Docker Compose setup)
- **Storage**: Persistent Docker volume `postgres_data` or your PostgreSQL server
- **When to use**: Production environments with multiple API/worker instances

> **💡 Switching databases**: Simply set or remove `DATABASE_URL` in your `.env` file. If not set, Ada defaults to SQLite.

### Resetting History
**SQLite:**
```bash
rm ada_jobs.db
python -c "from api.database import init_db; init_db()"
```

**PostgreSQL (Docker):**
```bash
docker-compose down -v  # -v removes the persistent volume
```

---

## 💻 Usage

### 🏭 Autonomous API Factory
Dispatch a story to the worker queue:
```bash
curl -X POST "http://localhost:8000/api/v1/execute" \
     -H "X-Api-Key: your-api-key-here" \
     -H "Content-Type: application/json" \
     -d '{
           "repo_url": "https://github.com/owner/repo",
           "stories": [{"story_id": "S1", "title": "Add a /health endpoint"}]
         }'
```

> **Note**: The `X-Api-Key` header is required when `API_KEYS` is configured in your environment.

### 🖥️ CLI Mode
Run a backlog against a remote repo:
```bash
python3 run_sdlc.py --repo https://github.com/owner/repo --stories stories/backlog.json
```

Run a single story against a local repo:
```bash
python3 run_local.py stories/example_story.json ./my_repo
```

---

## � Webhooks & Automation

Ada integrates with your VCS platform via webhooks to enable closed-loop development:

- **Auto-Fix CI Failures**: When pipelines fail, Ada analyzes logs and pushes fixes automatically
- **PR Comment Processing**: Use `@ada-ai` in PR comments to request code changes
- **Real-Time Feedback**: Ada responds to human feedback and iterates on PRs

### Quick Setup

**GitHub:**
1. Repository → Settings → Webhooks → Add webhook
2. URL: `https://your-ada-instance.com/api/v1/webhooks/github`
3. Secret: Your `GITHUB_WEBHOOK_SECRET` value
4. Events: Pull requests, Issue comments, Workflow runs

**GitLab:**
1. Project → Settings → Webhooks
2. URL: `https://your-ada-instance.com/api/v1/webhooks/gitlab`
3. Secret: Your `GITLAB_WEBHOOK_SECRET` value
4. Triggers: Merge request events, Comments, Pipeline events

📖 **[Complete Webhook Setup Guide](docs/WEBHOOK_SETUP.md)** - Detailed instructions for both platforms, troubleshooting, security best practices, and advanced configuration.

---

## 📁 Project Structure

```
ada/
├── run_sdlc.py                   # Full SDLC runner (clones repo → PR)
├── run_local.py                  # Local story runner (runs on existing folder)
├── api/
│   ├── main.py                   # FastAPI Story intake
│   ├── database.py               # PostgreSQL & SQLAlchemy setup
│   └── webhooks/                 # VCS Webhook handlers (GitHub, etc)
├── agents/
│   ├── base_agent.py             # Agent base class with history management
│   ├── coding_agent.py           # Senior autonomous Coder (Plan + Code)
│   ├── planning_agent.py         # Interactive requirement clarification
│   ├── validation_agent.py       # Autonomous Auditor and QA
│   └── llm/                      # LLM client wrappers & key rotation
├── planning/                     # Phase 3: Deterministic Planning
│   ├── models.py                 # ImplementationPlan, Task, TaskGraph, RunExecution
│   ├── planner_agent.py          # Story → ImplementationPlan with atomic tasks
│   ├── task_graph.py             # DAG builder, cycle detection, topological sort
│   └── task_scheduler.py         # Dependency-aware task dispatch with retries
├── orchestration/                # Phase 3: Plan-driven orchestration
│   └── plan_orchestrator.py      # Plan → TaskGraph → Schedule → Execute → Verify
├── execution/                    # Phase 3: Task execution engine
│   └── run_execution.py          # Isolated workspace per task, pipeline runner
├── verification/                 # Phase 3: Deterministic verification
│   └── quality_gate.py           # Auto-detected lint/build/test pipeline
├── intelligence/                 # Phase 4: Repository Intelligence Layer
│   ├── repo_scanner.py           # Filesystem walk, language detection, filtering
│   ├── ast_parser.py             # Tree-sitter AST parsing (Python/JS/TS/Go/Java)
│   ├── symbol_extractor.py       # AST nodes → graph nodes (classes, functions)
│   ├── dependency_analyzer.py    # Edge extraction (imports, contains, tests)
│   ├── repo_graph_builder.py     # Full pipeline, JSON persistence, incremental updates
│   └── context_retriever.py      # Task-aware keyword→graph→score→top-k retrieval
├── orchestrator/
│   ├── sdlc_orchestrator.py      # Git lifecycle & PR management
│   ├── epic_orchestrator.py      # Multi-story backlog execution (legacy)
│   └── task_executor.py          # Pipeline loop & agent chaining
├── tools/
│   ├── tools.py                  # Core filesystem & command tools
│   ├── git_manager.py            # High-level Git operations
│   ├── vcs_client.py             # Abstract VCS interface & factory
│   ├── github_client.py          # GitHub API implementation
│   └── gitlab_client.py          # GitLab API implementation
├── isolation/
│   ├── sandbox.py                # Local filesystem isolation
│   ├── docker_backend.py         # Container-based isolation
│   └── ecs_backend.py            # AWS ECS (Fargate) isolation
├── utils/
│   └── logger.py                 # Multi-destination logging (UI, Redis, DB)
└── docs/
    └── WEBHOOK_SETUP.md          # Comprehensive webhook configuration guide
```

---

**Happy Coding!** Point Ada at your repo, hand it a backlog, and go get a coffee. ☕
