# Ada - Autonomous AI Software Engineering Team

Ada is a multi-agent AI system that integrates directly into the software development lifecycle. By treating the agent as a longitudinal autonomous engineer, Ada processes full User Stories end-to-end: exploring code, planning implementation, writing changes, and opening Pull Requests — all without human intervention.

---

## 🚀 Features

- **Senior Autonomous Logic**: Ada behaves as a senior engineer — exploring code, creating internal monologues, and following a strict Plan-before-Code discipline.
- **Full SDLC Integration**: Provide a GitHub URL and a backlog. Ada clones, branches, codes, commits, and opens PRs automatically.
- **Pluggable Isolation (Prod-Ready)**: Support for multiple execution backends:
    - **Sandbox**: Lightweight local folder isolation.
    - **Docker**: Container-level isolation per story.
    - **AWS ECS (Fargate)**: True hardware-level isolation for untrusted code execution.
- **Production-Grade Persistence**: Moves from SQLite to **PostgreSQL** for reliable, concurrent data management in distributed environments.
- **High Autonomy (80+ Tool Calls)**: Ada is equipped with a large tool-call budget, allowing for massive refactors and multi-file changes in one session.
- **Parallel Backlog Execution**: Distribute multiple User Stories across a cluster of workers. Ada can process an entire backlog in parallel, horizontally scaling to meet your team's velocity.
- **Template-Driven PRs**: Generates structured PRs using `.ada/pr_template.md`, including completed tasks and file diff summaries.
- **VCS Webhook Support**: Generalized webhook architecture supporting GitHub (and soon Bitbucket/Azure) for automated feedback loops.
- **Closed-Loop Development**:
    - **CI/CD Auto-Fix**: Ada listens to VCS Webhooks. If a CI pipeline fails, she automatically downloads log artifacts, reproduces the bug, and pushes a patch.
    - **Human Feedback**: Comment on an Ada PR, and she will autonomously apply your requested changes and push the update.
- **Real-time Engineering Audit**: Follow Ada's reasoning in the Console UI with live streaming of tool calls, outputs, and internal "monologues".
- **LLM Support**: Built-in support for **Groq** (extremely fast) and **OpenAI**.

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
│    (Horizontal Scaling • One Task per ECS/Docker Sandbox)  │
└───────────┬───────────────────┬────────────────────────────┘
            │                   │
            │ [5] Reason        │ [6] Stream Logs (Pub/Sub)
            ▼                   ▼
┌──────────────────────┐    ┌──────────────────────┐
│ Isolation Backend    │    │   Redis (logs:id)    │
│ (Sandbox / ECS)      │    │   (SSE to Browser)   │
└──────────────────────┘    └──────────────────────┘
```

> **Note on Log Streaming**: While stories are queued via **Celery**, logs bypass the task queue and use **Redis Pub/Sub** for real-time streaming. The API subscribes to these logs and pushes them to the UI via Server-Sent Events (SSE), ensuring zero-latency monitoring.

### Execution Pipeline (The Story Lifecycle)
1. **Bootstrap**: `SDLCOrchestrator` clones the repo and creates a feature branch.
2. **Isolation**: Re-configurable backends (Sandbox, Docker, or ECS) ensure zero-side effects.
3. **Reasoning**: `CodingAgent` (Ada) researches, plans, and edits code until the Story is complete.
4. **Validation**: `ValidationAgent` ensures Acceptance Criteria and Global Rules are met.
5. **Finalization**: `GitManager` commits changes, pushes to origin, and `GitHubClient` opens the PR.

---

## 🛠 Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp env.example .env
```

#### LLM Keys (Groq recommended)
```bash
GROQ_API_KEY=gsk_your_key_here
GITHUB_TOKEN=ghp_your_pat_here
OPENAI_API_KEY=sk_your_key_here (optional, if using OpenAI)
```

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
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql://ada_user:ada_password@db:5432/ada_db
ADA_TMP_DIR=/tmp/ada_runs
```

### 3. Build & Run (Docker Compose)
The easiest way to run the full Ada factory (API + Redis + Postgres + Workers):
```bash
docker-compose up --build
```
*Live docs: [http://localhost:8000/docs](http://localhost:8000/docs)*

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

Ada uses **PostgreSQL** to track job history and logs. When running via Docker, this is stored in a persistent volume.

- **Storage**: Persistent Docker volume `postgres_data`.
- **Wait-on-Start**: Workers and API automatically wait for the Postgres health check before booting.

### Resetting History
To clear all job history and reset the database:
```bash
docker-compose down -v
```
*(The `-v` flag removes the named volume containing the database file.)*

---

## 💻 Usage

### 🏭 Autonomous API Factory
Dispatch a story to the worker queue:
```bash
curl -X POST "http://localhost:8000/api/v1/execute" \
     -H "Content-Type: application/json" \
     -d '{
           "repo_url": "https://github.com/owner/repo",
           "stories": [{"story_id": "S1", "title": "Add a /health endpoint"}]
         }'
```

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
│   ├── validation_agent.py       # Autonomous Auditor and QA
│   └── llm_client.py             # Groq/OpenAI client wrappers
├── orchestrator/
│   ├── sdlc_orchestrator.py      # Git lifecycle & PR management
│   ├── epic_orchestrator.py      # Multi-story backlog execution
│   └── task_executor.py          # Pipeline loop & agent chaining
├── tools/
│   ├── tools.py                  # Core filesystem & command tools
│   ├── git_manager.py            # High-level Git operations
│   └── github_client.py          # GitHub API integration
└── isolation/
    ├── sandbox.py                # Local filesystem isolation
    ├── docker_backend.py         # Container-based isolation
    └── ecs_backend.py            # AWS ECS (Fargate) isolation (NEW)
└── utils/
    └── logger.py                 # Multi-destination logging (UI, Redis, DB)
```

---

**Happy Coding!** Point Ada at your repo, hand it a backlog, and go get a coffee. ☕
