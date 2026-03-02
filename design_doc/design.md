# Ada: Autonomous AI Software Engineering Team — Design Document

Ada is an autonomous AI system that integrates directly into the software development lifecycle. By treating the agent as a senior developer with full longitudinal autonomy, Ada plans, codes, self-corrects, and opens pull requests — all without human intervention.

---

## 1. Philosophy

- **Long-Context Autonomy** — Ada is treated as a senior engineer. Instead of following small, brittle scripted tasks, Ada processes the entire User Story in a single, continuous execution window.
- **Direct Execution** — As LLMs improve, pre-planning agents became a bottleneck. Ada now explores the codebase, formulates a plan, and executes it step-by-step within her internal reasoning loop.
- **Isolated Self-Correction** — Coding failures feed back into the agent's context automatically. Quality is enforced by the agent's own internal verification tool-calling (running tests, reading files).
- **Zero Friction** — Integration is seamless: GitHub URLs in, structured Pull Requests out.

---

## 2. Architecture

Ada is layered. Each layer delegates inward, with clear handoffs.

```
run_sdlc.py         → SDLCOrchestrator      (VCS lifecycle per story)
run_epic.py         → EpicOrchestrator      (sequential story execution)
run_ada.py          → SandboxBackend        (single story execution)
                       └─ PipelineOrchestrator
                            └─ CodingAgent  (Plan + Code loop)
```

---

## 3. Agents

| Agent | Input | Output |
|---|---|---|
| `CodingAgent` | User Story + repo access | Modified files + self-verified tests |
| `ValidationAgent` | `.rules/` quality gate files | (Used in specialized/future audit layers) |

All agents share a common `BaseAgent` interface with a single `run(story, repo_path, context)` method and return an `AgentResult(success, output, context_updates)`.

---

## 4. SDLC Flow (Direct Mode)

```
Input:
  - GitHub repo URL
  - stories.json (Full User Story backlog)

SDLCOrchestrator:
  1. Clone repo                         (GitManager)
  2. For each story:
     a. Create branch: ada/<STORY-ID>-<slug>
     b. SandboxBackend: copy repo → start fresh isolation
     c. CodingAgent:
          - Explore codebase
          - Formulate implementation plan
          - Execute code changes sequentially
          - Run tests to verify work
     d. git commit (structured message based on Acceptance Criteria)
     e. git push
     f. GitHub API → open Pull Request  (GitHubClient + .ada/pr_template.md)
```

---

## 5. Key Design Decisions

| Decision | Rationale |
|---|---|
| **Direct Story Mode** | Pre-generated task JSONs were fragile. Large context windows allow the agent to handle planning and execution in one fluent session. |
| **Tool-Driven Verification** | The agent is instructed to write and run her own tests to verify changes before declaring a story "finished." |
| **80+ Tool Call Limit** | Entire stories are complex. Expanding the reasoning limit ensures Ada can handle large, multi-file refactors. |
| **Generalized VCS Webhooks** | Renamed to `VCSWebhooks` to support future providers (Bitbucket, GitLab) while keeping the same "Auto-Fix" logic. |
| **Structured PR Template** | PRs aren't just code; they include checkboxes for acceptance criteria and a detailed list of modified files for reviewers. |

---

## 6. Closed-Loop Development

Ada doesn't stop after the PR:
- **CI/CD Auto-Fix**: Ada listens to VCS webhooks. If a CI pipeline fails, she fetches the runner logs, clones the exact commit state, fixes the bug, and pushes a patch.
- **Human Feedback**: Reviewer comments on a PR trigger Ada to re-evaluate the code, apply the requested changes, and push updates autonomously.

---

## 7. Extension Points

- **New provider** → add a route in `api/webhooks/vcs.py` and a method in `GitHubClient` (or a more generic client).
- **New LLM provider** → register a client in `Config.get_llm_client()`.
- **Audit Layer** → re-integrate `ValidationAgent` into the `PipelineOrchestrator` to enforce specialized rulesets.

---

## 8. Future Enhancements

- **PR Review Agent**: A specialized agent that reviews other PRs or self-reviews before opening.
- **Dependency Graphing**: Automated mapping of the code before implementation begins.
- **Self-Healing Infrastructure**: Detecting deployment errors and reverting or fixing them.
