# Ada - Autonomous AI Software Engineering Team

Ada is a multi-agent AI system that integrates directly into the software development lifecycle. Given a GitHub repository URL and a backlog of User Stories, Ada autonomously clones the project, plans and writes the code, validates it against your quality rules, and opens a Pull Request — all without human intervention.

---

## 🚀 Features

- **Full SDLC Integration**: Provide a GitHub URL and a backlog. Ada clones, branches, codes, commits, and opens PRs automatically.
- **Multi-Agent Pipeline**: Specialized agents — `PlanningAgent`, `CodingAgent`, `ValidationAgent` — each with a focused, autonomous role.
- **Epic-Level Orchestration**: Feed a full Agile backlog and Ada breaks each story into atomic tasks, executes them sequentially, and persists the results.
- **Global Quality Gates**: Drop `.md` or `.txt` files into `.rules/` to define engineering standards. The `ValidationAgent` enforces these on every task.
- **Git & GitHub Integration**: Creates feature branches per story, commits with structured messages, pushes, and opens PRs using a configurable template.
- **Isolated Sandbox Execution**: Each task runs in its own isolated workspace, copied fresh from the current repo state. Results merge back sequentially.
- **LLM Support**: Auto-detects **Groq** (recommended, extremely fast) or **OpenAI** from your environment keys.
- **Observability**: Rich ANSI-coloured terminal output with agent thoughts, tool calls, byte-level result summaries, and retry explanations.
- **Mock Mode**: Fully functional mock LLM layer for testing without consuming API credits.

---

## 🏛 Architecture

```
┌───────────────────────────────────────┐    ┌───────────────────────────────────────┐
│  API & Async Workers (api.main:app)   │    │  CLI Scripts (Standalone Mode)        │
│  FastAPI → Redis Queue → Celery       │    │  run_sdlc.py | run_epic | run_ada   │
└──────────────────┬────────────────────┘    └──────────────────┬────────────────────┘
                   │                                            │
                   └──────────────────────┬─────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────────┐
│  SDLCOrchestrator     (orchestrator/sdlc_orchestrator.py)           │
│                                                                     │
│  1. GitManager.clone(url)             → workspace/repo/             │
│  2. For each story:                                                  │
│     a. GitManager.create_branch()     → ada/<story-id>-<slug>       │
│     b. EpicOrchestrator.execute()     → plan + sandboxed execution  │
│     c. GitManager.commit() + push()   → structured commit message   │
│     d. GitHubClient.create_pr()       → PR from template            │
│  3. Workspace cleanup                 → success: clean | fail: keep │
└─────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│  EpicOrchestrator     (orchestrator/epic_orchestrator.py)           │
│                                                                     │
│  Per story:                                                          │
│  1. PlanningAgent scans repo → generates [T1, T2, T3] as JSON       │
│  2. Saves tasks to  tasks/<STORY-ID>/<task_id>.json                 │
│  3. Runs each task sequentially inside a fresh SandboxBackend       │
└─────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│  SandboxBackend    (isolation/sandbox.py)   [per task]              │
│                                                                     │
│  • Copies repo → .ada_sandbox/task_<id>/repo                       │
│  • Runs PipelineOrchestrator  [CodingAgent → ValidationAgent]       │
│  • Copies results back to repo (so next task sees updated code)     │
└─────────────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────────┐
              │                                  │
┌─────────────▼──────────────┐     ┌────────────▼───────────────────┐
│  CodingAgent               │     │  ValidationAgent               │
│  agents/coding_agent.py    │     │  agents/validation_agent.py    │
│                            │     │                                │
│  • Reasons with LLM        │     │  • Reads .rules/ quality gates │
│  • Writes and edits files  │     │  • Outputs PASS or FAIL        │
│  • Runs verification cmds  │     │  • Feeds back to CodingAgent   │
│  • Declares "finish"       │     │    for up to 25 retry cycles   │
└────────────────────────────┘     └────────────────────────────────┘
```

### Agent Responsibilities

| Agent | Role |
|---|---|
| `PlanningAgent` | Reads the codebase and translates a User Story into an ordered list of atomic tasks |
| `CodingAgent` | Autonomously writes code, runs commands, and verifies changes locally |
| `ValidationAgent` | Scans the codebase against `.rules/` quality gates; outputs `PASS` or `FAIL` |

### Orchestration Layers

| Orchestrator | Scope | Entry Point |
|---|---|---|
| `SDLCOrchestrator` | Full lifecycle: git → agents → PR | `run_sdlc.py` |
| `EpicOrchestrator` | Story backlog: plan → persist tasks → sandbox loop | `run_epic.py` |
| `PipelineOrchestrator` | Single task: agent pipeline with retry | internal |
| `SandboxBackend` | Filesystem isolation per task | internal |

### Per-Story Git Lifecycle

```
For each User Story:

  1.  git checkout -b ada/STORY-1-password-reset

  2.  PlanningAgent scans codebase
      → saves tasks/STORY-1/STORY1-T1.json, STORY1-T2.json ...

  3.  For each task (sequential):
        SandboxBackend isolates → CodingAgent codes → ValidationAgent gates
        → merge results back to branch working tree

  4.  git add . && git commit -m "feat(STORY-1): Add password reset via email
                                  - ✅ User can request reset link ..."

  5.  git push origin ada/STORY-1-password-reset

  6.  GitHub API → create PR
        Title:  "[Ada] STORY-1: Add password reset via email"
        Body:   filled from .ada/pr_template.md
        Base:   main (configurable)
        Draft:  if story was only partially successful
```

### Global Quality Rules

Drop `.md` or `.txt` files into `.rules/` to define project-wide engineering standards. These are loaded at runtime by `LocalFolderRuleProvider` and injected into every `ValidationAgent` run.

```
.rules/
  code_standard.md       ←  "Never hardcode secrets. Always use env vars."
  api_conventions.md     ←  "All endpoints must return JSON with a status field."
  testing_policy.md      ←  "Every new endpoint must have at least one unit test."
```

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

#### LLM Keys

Ada auto-detects your provider based on which key is present. Groq is recommended — it's free and extremely fast.

```bash
# Groq (recommended) — https://console.groq.com/keys
GROQ_API_KEY=gsk_your_key_here

# OpenAI (optional fallback)
OPENAI_API_KEY=sk_your_key_here
```

You can force a specific provider regardless of which keys are present:

```bash
LLM_PROVIDER=openai   # or: groq | mock
```

#### GitHub Token (required for `run_sdlc.py` only)

`GITHUB_TOKEN` is a **Personal Access Token (PAT)** — a scoped API key that lets Ada push branches and open Pull Requests on your behalf via the GitHub REST API.

**How to get one:**

1. Go to **[github.com/settings/tokens](https://github.com/settings/tokens)**
2. Click **"Generate new token (classic)"**
3. Give it a note like `Ada AI Agent` and choose an expiration
4. Under **Scopes**, check only ✅ **`repo`** (full control of repositories)
5. Click **"Generate token"** — copy it immediately, it is only shown once

Add it to your `.env`:

```bash
GITHUB_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456
```

> **Note:** `GITHUB_TOKEN` is only required when running `run_sdlc.py`. The `run_ada.py` and `run_epic.py` scripts work entirely without it.

### 3. Add quality rules (optional but recommended)

Create a `.rules/` directory in the project root and drop in `.md` or `.txt` files. Ada's `ValidationAgent` will enforce these standards on every task:

```bash
mkdir .rules

# Example rules
echo "Never hardcode secrets. Always use environment variables." > .rules/security.md
echo "Every new API endpoint must return JSON with a 'status' field." > .rules/api.md
echo "All new functions must have a docstring." > .rules/style.md
```

### 4. (Optional) Build the Docker image

For fully containerised task isolation:

```bash
docker build -f docker/Dockerfile -t ada_agent_mvp .
```

---

## 💻 Usage

### 🏭 Autonomous Software Factory (Concurrent API Mode)

Ada includes a robust backend architecture (FastAPI + Celery + Redis + SQLite) designed for high-throughput, parallel execution of stories in completely isolated sandboxes. This is perfect for local multi-tasking or deploying as a scalable cloud service.

#### The Easy Way: Docker Compose
Boot up the entire factory (Redis, API Server, and Celery Workers) with a single command:
```bash
docker-compose up --build
```
*Your interactive API documentation is now live at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)*

<details>
<summary><b>The Manual Way: Bare Metal Startup</b></summary>

**1. Start the Message Broker (Redis)**
```bash
docker run -d -p 6379:6379 redis
```
**2. Start the API Server**
```bash
uvicorn api.main:app --reload
```
**3. Start the Parallel Workers**
```bash
celery -A worker.tasks worker --loglevel=info --concurrency=4
```
</details>

**Dispatch a Story**
You can now send POST requests to the API. The workers will immediately pick them up, spin up ephemeral `/tmp` sandboxes, clone the repo, write the code, and open PRs completely in parallel.
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/execute" \
     -H "Content-Type: application/json" \
     -d '{
           "repo_url": "https://github.com/owner/repo",
           "stories": [
             {
               "story_id": "STORY-1",
               "title": "Add an API endpoint",
               "acceptance_criteria": ["Endpoint returns 200"]
             }
           ]
         }'
```

---

### 🖥️ CLI Mode — Clone, code, commit, and open PRs

```bash
python3 run_sdlc.py \
  --repo https://github.com/owner/repo \
  --stories stories/epic_backlog.json \
  --base-branch main \
  --workspace .ada_workspace \
  --clean              # optional: force-clean workspace even on failure
```

| Flag | Default | Description |
|---|---|---|
| `--repo` | *(required)* | GitHub repository URL (HTTPS or SSH) |
| `--stories` | *(required)* | Path to a JSON file with one or more User Stories |
| `--base-branch` | `main` | Branch that PRs will target |
| `--workspace` | `.ada_workspace` | Local directory for Ada's working files |
| `--clean` | `false` | Force-clean workspace after run, even on failure |

Ada will:
1. Clone the repository into `.ada_workspace/repo/`
2. For each story: create a feature branch → plan → code → validate → commit → push → open PR
3. Clean up the workspace based on the outcome (see **Workspace Lifecycle** below)

#### Workspace Lifecycle

The `.ada_workspace/` directory holds the cloned repo and per-task sandbox copies. After a run completes, Ada manages cleanup automatically:

| Outcome | Default behaviour | With `--clean` |
|---|---|---|
| ✅ All stories succeed | 🧹 Workspace **deleted** | 🧹 Workspace **deleted** |
| ❌ Any story fails | 🔍 Workspace **preserved** for debugging | 🧹 Workspace **deleted** |

When the workspace is preserved on failure, Ada logs the path so you can inspect the cloned repo, branches, and partial changes:

```
[SDLCOrchestrator] 🔍 Workspace preserved for debugging: /path/to/.ada_workspace
[SDLCOrchestrator]    Re-run with --clean to force cleanup, or delete manually.
```

> **Note:** Per-task sandbox copies (inside `SandboxBackend`) are always cleaned up immediately after each task, regardless of success or failure. The workspace lifecycle above applies only to the top-level `.ada_workspace/` directory.

### Epic Mode — Run a full story backlog against a local repo

```bash
python3 run_epic.py stories/epic_backlog.json repo_snapshot
```

Ada will plan each story into atomic tasks (saved to `tasks/<STORY-ID>/`), then execute them sequentially in isolated sandboxes.

### Task Mode — Run a single atomic task

```bash
# Sandbox (local)
python3 run_ada.py tasks/task2_register.json repo_snapshot

# Docker isolation
python3 run_ada.py tasks/task2_register.json repo_snapshot --backend docker

# Mock LLM (no API credits)
python3 run_ada.py tasks/example_task.json repo_snapshot --mock
```

---

## 📝 Input Formats

### User Story (`stories/*.json`)

Used by `run_sdlc.py` and `run_epic.py`. Can be a single object or an array:

```json
[
  {
    "story_id": "STORY-1",
    "title": "As a user, I want to reset my password via email",
    "description": "Users need a secure way to request a reset link and set a new password.",
    "acceptance_criteria": [
      "User can submit their email to request a reset link.",
      "A secure, time-limited token is generated.",
      "User can submit a new password using the valid token."
    ]
  }
]
```

### Atomic Task (`tasks/*.json`)

Used directly by `run_ada.py`, or auto-generated by the `PlanningAgent`:

```json
{
  "task_id": "STORY1-T1",
  "title": "Add /forgot-password endpoint",
  "description": "Create a POST /forgot-password endpoint that accepts an email and generates a reset token.",
  "dependencies": [],
  "acceptance_criteria": [
    "POST /forgot-password accepts JSON with an email field.",
    "Returns 404 if the email is not registered.",
    "Returns 200 and logs/emails a reset token on success."
  ]
}
```

---

## 🧪 Testing

```bash
python3 -m pytest tests/
```

With coverage:

```bash
python3 -m pytest --cov --cov-report=term-missing tests/
```

---

## 📁 Project Structure

```
ada/
├── run_sdlc.py                   # Full SDLC runner: clone → code → PR
├── run_epic.py                   # Story/backlog runner
├── run_ada.py                    # Single task runner
├── config.py                     # LLM provider auto-detection
│
├── agents/
│   ├── base_agent.py             # BaseAgent interface + AgentResult type
│   ├── planning_agent.py         # User Story → ordered atomic task JSON
│   ├── coding_agent.py           # Autonomous code writing + verification
│   ├── validation_agent.py       # .rules/ quality gate enforcement
│   ├── llm_client.py             # Groq/OpenAI client wrapper
│   └── mock_llm_client.py        # Deterministic mock for unit tests
│
├── orchestrator/
│   ├── sdlc_orchestrator.py      # Git lifecycle wrapper around EpicOrchestrator
│   ├── epic_orchestrator.py      # Story-level: plan tasks → sequential sandboxes
│   ├── task_executor.py          # Task-level: agent pipeline + retry loop
│   └── rule_provider.py          # Loads .rules/ quality gate files from disk
│
├── tools/
│   ├── tools.py                  # File I/O, shell, and codebase search tools
│   ├── git_manager.py            # clone, branch, commit, push wrappers
│   └── github_client.py          # GitHub REST API: create PR, parse URLs
│
├── isolation/
│   ├── sandbox.py                # Filesystem-isolated sandbox + SandboxedTools
│   └── backend.py                # Abstract isolation backend interface
│
├── .rules/                       # Global quality gate rule files
│   └── code_standard.md
│
├── .ada/                         # Ada configuration and templates
│   └── pr_template.md            # PR body template for GitHub PRs
│
├── stories/                      # User story definitions
│   ├── epic_backlog.json         # Example multi-story backlog
│   └── example_story.json        # Single story example
│
├── tasks/                        # Atomic task JSON files
│   ├── task2_register.json       # Hand-written examples
│   └── <STORY-ID>/               # Auto-generated by PlanningAgent
│       └── <task_id>.json
│
├── docker/                       # Docker isolation backend
│   ├── Dockerfile
│   └── entrypoint.py
│
├── design_doc/
│   └── design.md                 # Architecture and design principles
│
└── tests/                        # pytest unit test suite
```

---

**Happy Coding!** Point Ada at your GitHub repo, hand it a backlog, and go get a coffee. ☕
