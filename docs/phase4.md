
---

# ADA Coding Agent – Phase 4 Design Document

**Phase 4: Repository Intelligence Layer**

Version: `v0.4`
Last Updated: 2026-03-12

---

## 1. Purpose

Phase 4 adds a **Repository Intelligence Layer** that allows ADA Coding Agent to:

* Understand repository architecture
* Identify relevant code automatically
* Reduce hallucinated edits
* Plan tasks based on real dependencies
* Safely modify large codebases

This layer transforms the repository from **plain files** into a **structured knowledge graph** that agents can reason over.

---

## 2. High-Level Architecture

```
User Story
     │
     ▼
Planning Agent
     │
     ▼
Repository Intelligence Layer
     │
     ▼
Task Graph
     │
     ▼
Scheduler
     │
     ▼
Execution Engine
     │
     ▼
Coding Agent
     │
     ▼
Verification & Feedback
```

**Key Components:**

1. Repo Scanner
2. Static Code Parser (Tree-sitter)
3. Symbol Extractor
4. Dependency Analyzer
5. Repository Knowledge Graph Builder
6. Context Retrieval Engine

---

## 3. Repository Knowledge Graph

### Node Types

* Repository
* Directory
* File
* Class
* Function / Method
* API Endpoint
* Database Table
* Test
* Config

### Edge Types

* `imports`
* `calls`
* `extends` / `implements`
* `depends_on`
* `reads` / `writes`
* `tests`

**Example Graph:**

```
AuthController
     │ calls
     ▼
UserService
     │ calls
     ▼
UserRepository
     │ reads
     ▼
UsersTable
```

---

## 4. Repo Scanner

Walks the repository filesystem and collects relevant files.

* Supported languages (initial MVP): Python, TypeScript, JavaScript, Go, Java
* Pseudo code:

```python
scan_repository(repo_path):
    for file in repo:
        if language_supported(file):
            send_to_parser(file)
```

---

## 5. Static Code Parser

* Uses **Tree-sitter** for AST parsing
* Extracts:

  * Classes
  * Functions
  * Methods
  * Imports

**Output example:**

```json
{
  "file": "user_service.py",
  "classes": ["UserService"],
  "functions": ["reset_password"],
  "imports": ["UserRepository"]
}
```

---

## 6. Symbol Extractor

* Converts AST nodes to **graph nodes**
* Example node:

```json
{
  "id": "reset_password",
  "type": "function",
  "file": "user_service.py"
}
```

---

## 7. Dependency Analyzer

* Extracts relationships between nodes:

```python
UserService -> imports -> UserRepository
AuthController -> calls -> UserService
```

* Builds edges in the repository knowledge graph

---

## 8. Graph Storage

* MVP: JSON (`repo_graph.json`)
* Future: Graph DB (Neo4j, ArangoDB, or Postgres graph extension)

---

## 9. Context Retrieval Engine

* Agents request **task-specific context** instead of the entire repo
* Steps:

1. Extract keywords from task
2. Match relevant nodes in graph
3. Traverse dependency edges
4. Score nodes by relevance
5. Return top-k nodes/files as structured context

**Example returned context:**

```json
{
  "task": "Add password reset endpoint",
  "relevant_files": [
    "auth_controller.py",
    "user_service.py"
  ],
  "related_symbols": [
    "UserService",
    "AuthController"
  ],
  "dependencies": [
    "UserRepository"
  ]
}
```

---

## 10. Graph Updates

* Trigger: `git commit` / repo changes
* Rebuild only changed files
* Update nodes, edges, and JSON or graph DB

---

## 11. Integration with Planning Agent

* Planning Agent receives:

  * Repository summary
  * Repo graph

* Can **enforce architecture rules**:

```
controllers cannot access database directly
services call repositories
tests required for new endpoints
```

* Rejects plans violating architecture

---

## 12. Integration with Coding Agent

* Coding Agent receives:

  * Task description
  * Relevant files and symbols
  * Dependencies
  * Architecture constraints

* Enables **precision edits** instead of blind modifications

---

## 13. Tools & Technology Stack

| Component           | Tool                   |
| ------------------- | ---------------------- |
| Parsing             | Tree-sitter            |
| Repo scanning       | Python filesystem      |
| Graph storage       | JSON → Neo4j (future)  |
| Context retrieval   | Custom engine          |
| Agent orchestration | Existing ADA framework |

**Optional:** Use **semantic embeddings** for very large repos (>10k files) combined with graph traversal.

---

## 14. Phase 4 Success Criteria

* Agents reliably identify relevant files
* Architecture constraints are enforced
* Context size is minimal but sufficient
* Hallucinated edits are significantly reduced
* System scales to medium-large repos (1k–10k files)

---

## 15. Repo Intelligence Module Layout

```
intelligence/
    repo_scanner.py
    ast_parser.py
    symbol_extractor.py
    dependency_analyzer.py
    repo_graph_builder.py
    context_retriever.py
```

---

## 16. Incremental Roadmap

* **Phase 4 MVP:** Basic graph, keyword + dependency retrieval, JSON storage
* **Phase 4.1:** Multi-language support, smarter scoring, limited embeddings
* **Phase 4.2:** Graph DB storage, architecture validation rules, caching for performance
* **Phase 5:** Self-improving retrieval based on prior successful edits

---
