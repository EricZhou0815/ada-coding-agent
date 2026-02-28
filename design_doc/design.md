# Ada: Autonomous AI Software Engineering Team — Design Document

Ada is an autonomous, multi-agent AI system that integrates directly into the software development lifecycle. Agents plan, code, validate, commit, and open pull requests — all without human intervention.

---

## 1. Philosophy

- **Human-like autonomy** — Ada is treated as a human engineer. Agents reason, plan, and self-correct rather than following rigid scripted steps.
- **Separation of concerns** — Each agent has one job. Planning, coding, and validation are independent, composable units.
- **Iterative quality** — Validation failures feed back into the coding loop automatically (up to 25 retries). Quality is enforced by rules, not by hardcoded checks.
- **Future-proof** — As LLMs improve, Ada improves. No core orchestration logic needs to change.

---

## 2. Architecture

Ada is layered. Each layer delegates inward, with clear handoffs.

```
run_sdlc.py         → SDLCOrchestrator    (git lifecycle per story)
run_epic.py         → EpicOrchestrator    (plan + sandbox loop per story)
run_ada.py          → SandboxBackend      (single task execution)
                       └─ PipelineOrchestrator
                            ├─ CodingAgent
                            └─ ValidationAgent
```

---

## 3. Agents

| Agent | Input | Output |
|---|---|---|
| `PlanningAgent` | User Story + codebase (read-only) | `tasks/<STORY-ID>/<task>.json` array |
| `CodingAgent` | Atomic task + context | Modified files in sandbox |
| `ValidationAgent` | `.rules/` quality gate files | `PASS` or `FAIL` + feedback |

All agents share a common `BaseAgent` interface with a single `run(task, repo_path, context)` method and return an `AgentResult(success, output, context_updates)`.

---

## 4. SDLC Flow

```
Human provides:
  - GitHub repo URL
  - stories/*.json  (User Story backlog)

SDLCOrchestrator:
  1. Clone repo                         (GitManager)
  2. For each story:
     a. Create branch: ada/<STORY-ID>-<slug>
     b. PlanningAgent → generates + saves atomic task JSONs
     c. For each task (sequential):
          SandboxBackend: copy repo → run [Coder → Validator] → merge back
     d. git commit (structured message)
     e. git push
     f. GitHub API → open Pull Request  (GitHubClient + .ada/pr_template.md)
```

---

## 5. Key Design Decisions

| Decision | Rationale |
|---|---|
| One sandbox per task | Clean isolation; results merge back so next task sees updated code |
| Tasks saved as JSON before execution | Inspectable, replayable, and hand-editable; decouples planning from execution |
| ValidationAgent uses only `.rules/` | Task acceptance criteria belong to the Coder's loop; rules are team-wide quality gates |
| GitHub token loaded from env | Never hardcoded; `GITHUB_TOKEN` in `.env` following the same pattern as LLM keys |
| No third-party HTTP libs for GitHub API | `urllib.request` only — zero extra dependencies |
| `slugify()` for branch names | Story titles become safe, human-readable branch names automatically |

---

## 6. Quality Gates

Drop `.md` or `.txt` files into `.rules/` at the repo root. They are loaded by `LocalFolderRuleProvider` and injected into every `ValidationAgent` run. No code changes needed to add or modify rules.

---

## 7. Extension Points

- **New agent** → implement `BaseAgent`, add to the pipeline list in `PipelineOrchestrator`
- **New LLM provider** → add a client in `agents/llm_client.py`, register in `Config.get_llm_client()`
- **New isolation backend** → implement `IsolationBackend`, drop it into `isolation/`
- **New rule source** → implement `RuleProvider`, pass to `PipelineOrchestrator`
- **Parallel stories** → `SDLCOrchestrator.run()` can be extended with `ThreadPoolExecutor` at the story level; tasks within a story must remain sequential

---

## 8. Future Enhancements

- Parallel story execution (story-level concurrency via threads)
- Dependency-aware task ordering (if task B depends on A, enforce ordering)
- PR review agent (reads the diff, adds inline review comments)
- CI/CD integration (trigger GitHub Actions on PR, read build status back into Ada)
- Knowledge graph tracking past tasks, decisions, and repo history
