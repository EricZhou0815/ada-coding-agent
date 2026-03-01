# Ada - Autonomous AI Software Engineering Team

Ada is a multi-agent AI system that integrates directly into the software development lifecycle. By treating the agent as a longitudinal autonomous engineer, Ada processes full User Stories end-to-end: exploring code, planning implementation, writing changes, and opening Pull Requests — all without human intervention.

---

## 🚀 Features

- **Direct Story Execution**: Eliminate brittle task-generation steps. Ada's `CodingAgent` handles the entire User Story lifecycle (Research → Plan → Code → Verify) in a single high-context window.
- **Full SDLC Integration**: Provide a GitHub URL and a backlog. Ada clones, branches, codes, commits, and opens PRs automatically.
- **High Autonomy (80+ Tool Calls)**: Ada is equipped with a large tool-call budget, allowing for massive refactors and multi-file changes in one session.
- **Git & GitHub Integration**: Creates feature branches per story with human-readable slugs, commits with structured messages, and opens PRs using a configurable template.
- **VCS Webhook Support**: Generalized webhook architecture supporting GitHub (and soon Bitbucket/Azure) for automated feedback loops.
- **Closed-Loop Development**:
    - **CI/CD Auto-Fix**: Ada listens to VCS Webhooks. If a CI pipeline fails, she automatically downloads log artifacts, reproduces the bug, and pushes a patch.
    - **Human Feedback**: Comment on an Ada PR, and she will autonomously apply your requested changes and push the update.
- **Isolated Sandbox Execution**: Each story runs in a clean, ephemeral sandbox, ensuring zero side effects on the host or other tasks.
- **LLM Support**: Built-in support for **Groq** (extremely fast) and **OpenAI**.

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
│  SDLCOrchestrator     (orchestrator/sdlc_orchestrator.py)                          │
│                                                                                    │
│  1. GitManager.clone(url)             → workspace/repo/                            │
│  2. For each story:                                                                │
│     a. GitManager.create_branch()     → ada/<story-id>-<slug>                      │
│     b. EpicOrchestrator.execute()     → direct sandboxed execution                 │
│     c. GitManager.commit() + push()   → structured commit message                  │
│     d. GitHubClient.create_pr()       → PR from template                           │
└─────────────────────────────────────────┬──────────────────────────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  │                                               │
┌─────────────────▼───────────────┐               ┌───────────────▼─────────────────┐
│  VCS WEBHOOKS (Auto-Fix)        │               │  SDLC PIPELINE (Backlog)        │
│  api/webhooks/vcs.py            │               │  orchestrator/epic_orch...      │
└────────────────┬────────────────┘               └───────────────┬─────────────────┘
                 │                                                │
                 └──────────────────────┬─────────────────────────┘
                                        │
┌───────────────────────────────────────▼───────────────────────────────────────┐
│  NEXT.JS CONSOLE UI (ui/)                                                     │
│  Interactive dashboard for dispatching stories and streaming logs.            │
└───────────────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│  SandboxBackend    (isolation/sandbox.py)   [per story]             │

│                                                                     │
│  • Copies repo → .ada_sandbox/story_<id>/repo                      │
│  • Runs PipelineOrchestrator  [CodingAgent]                         │
│  • Direct Execution: Exploration, Planning & Coding in one session  │
└─────────────────────────────────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  CodingAgent    │
                    │  (Plan + Code)  │
                    └─────────────────┘
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

#### LLM Keys (Groq recommended)
```bash
GROQ_API_KEY=gsk_your_key_here
GITHUB_TOKEN=ghp_your_pat_here
```

### 3. Build & Run (Docker Compose)
The easiest way to run the full Ada factory (API + Redis + Workers):
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
│   └── webhooks/vcs.py           # Provider-agnostic webhook handlers (GitHub, etc)
├── agents/
│   ├── coding_agent.py           # Single agent for Plan + Code loop
│   ├── validation_agent.py       # (Audit layer / reserved for future use)
│   └── llm_client.py             # Groq/OpenAI client wrappers
├── orchestrator/
│   ├── sdlc_orchestrator.py      # Git lifecycle management
│   ├── epic_orchestrator.py      # Sequential story execution
│   └── task_executor.py          # Pipeline loop + retry logic
└── isolation/
    ├── sandbox.py                # Local filesystem isolation
    └── docker_backend.py         # Container-based isolation
```

---

**Happy Coding!** Point Ada at your repo, hand it a backlog, and go get a coffee. ☕
