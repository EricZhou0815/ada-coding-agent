# Ada - Autonomous AI Software Engineer - built by AI

Ada is an autonomous AI agent capable of executing complex programming tasks in an isolated environment. It uses LLMs (like Groq or OpenAI) to analyze prompts, explore codebases, and write solutions.

It offers pluggable isolation backends (Sandbox and Docker) to run commands and make changes safely without affecting the host machine un-intendedly.

## 🚀 Features

- **LLM Support**: Built-in support for **Groq** via OpenAI compatibility (extremely fast!) and standard OpenAI models.
- **Isolated Execution Backends**: 
  - **Docker Backend**: Runs the agent and repository completely isolated inside a throw-away container.
  - **Sandbox Backend**: Runs locally with directory containment.
- **Agent Roles**: Split into specialized Coding and Validation agents.
- **Automated Workspaces**: Safely copies repository snapshots and creates scratch directories.
- **Mock Mode**: Fully functional mock LLM layer to test agent flows without consuming API credits.

## 🛠 Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy the example environment configuration:

```bash
cp .env.example .env
```

Open `.env` and fill in your API key. 
> **Tip:** We heavily recommend using [Groq](https://console.groq.com/keys) as it is set as the default provider and offers incredible iteration speeds.

### Configuration / LLM Provider
Ada uses a centralized configuration system (`config.py`). By default, it auto-detects your provider based on your API keys (`GROQ_API_KEY` prioritizes over `OPENAI_API_KEY`). 

You can explicitly force a provider without removing keys by setting the `LLM_PROVIDER` variable in your `.env` or shell:

```bash
# Force OpenAI even if Groq key is present
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-yourkey...
# GROQ_API_KEY=gsk_yourkey...
```

Valid `LLM_PROVIDER` values are: `groq`, `openai`, or `mock`.

### 3. Build the Docker Image (If using Docker backend)

If you plan to use isolated container execution, build the worker image:

```bash
docker build -f docker/Dockerfile -t ada_agent_mvp .
```

---

## 💻 Usage

Ada is executed using the unified runner `run_ada.py`. You provide a task description (JSON) and a codebase path.

### Basic Execution (Sandbox)
```bash
python3 run_ada.py tasks/example_task.json repo_snapshot
```

### Isolated Execution (Docker)
```bash
python3 run_ada.py tasks/example_task.json repo_snapshot --backend docker
```

*(Note: ensure your shell environment has loaded your `.env` variables before running so `run_ada.py` can pass them!)*

### Test run with Mock API
Don't want to use real LLM tokens while debugging the runner infrastructure? Use `--mock`:

```bash
python3 run_ada.py tasks/example_task.json repo_snapshot --mock
```

---

## 🧪 Testing

Ada comes with a comprehensive suite of isolated unit tests covering configurations, tool endpoints, agent loops, and orchestrators. 

To execute the test suite, ensure you have the `pytest` dependency installed, and run:
```bash
python3 -m pytest tests/
```

### Coverage Reports
To execute the suite and return a terminal coverage matrix highlighting missed source lines:
```bash
pip install pytest-cov coverage
python3 -m pytest --cov --cov-report=term-missing tests/
```

---

## 📝 Writing Tasks

Tasks are JSON files containing instructions and acceptance criteria. You can find examples in the `/tasks` folder.

**Example Task Format:**
```json
{
  "task_id": "T1",
  "title": "Add JWT authentication to login",
  "description": "Update login endpoint to return signed JWT token upon successful authentication.",
  "dependencies": [],
  "acceptance_criteria": [
    "Valid token allows access to protected routes",
    "Requests without token return 401"
  ]
}
```

## 🏗 Project Structure

- `run_ada.py` - Primary CLI entry point.
- `isolation/` - Logic for Docker and Sandbox execution environments.
- `agents/` - LLM connection logic (`llm_client.py`), Coding, and Validation agents.
- `tools/` - Sandbox tools offered to the LLM via function-calling (file reading, writing, terminal).
- `orchestrator/` - Logic that coordinates agents and tool execution.
- `docker/` - Docker deployment configuration and entrypoint context for isolated runs.
- `tasks/` - Library of JSON tasks to orchestrate.

---

**Happy Coding!** Let Ada write your boilerplate.
