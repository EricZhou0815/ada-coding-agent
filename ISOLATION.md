# Ada Isolation Backends

This document explains how to use Ada's pluggable isolation backends.

## Quick Start

```powershell
# Run with sandbox (no Docker needed)
python run_ada.py tasks/example_task.json repo_snapshot --backend sandbox --mock

# Run with Docker (requires Docker Desktop)
python run_ada.py tasks/example_task.json repo_snapshot --backend docker
```

## Available Backends

### 1. Sandbox Backend (Default)
- **No Docker required** ✅
- Creates isolated workspace in `.ada_sandbox/`
- Restricts file access to sandbox directory
- Copies results back to original repo
- Command execution with timeouts and blacklists
- **Best for**: Quick testing, development, local use

### 2. Docker Backend
- **Requires Docker Desktop** 
- Full container isolation
- Automatically builds image if needed
- Maximum security isolation
- **Best for**: Production, untrusted code, CI/CD

## Command Line Options

```
python run_ada.py <task_file> <repo_path> [options]

Options:
  --backend {sandbox,docker}  Choose isolation backend (default: sandbox)
  --mock                      Use mock LLM (no API key needed)
  --keep-workspace            Keep sandbox workspace for debugging
```

## Examples

**Demo with mock LLM (no API key):**
```powershell
python run_ada.py tasks/example_task.json repo_snapshot --mock
```

**Production with OpenAI:**
```powershell
$env:OPENAI_API_KEY='sk-...'
python run_ada.py tasks/example_task.json repo_snapshot --backend sandbox
```

**Debug mode (keep workspace):**
```powershell
python run_ada.py tasks/example_task.json repo_snapshot --keep-workspace
```

**Docker isolation:**
```powershell
python run_ada.py tasks/example_task.json repo_snapshot --backend docker
```

## Security Features

### Sandbox Backend
- ✅ File access restricted to sandbox directory
- ✅ Dangerous commands blacklisted
- ✅ Command execution timeout (30s)
- ✅ Workspace isolation from host
- ✅ Results copied back selectively

### Docker Backend
- ✅ Full OS-level isolation
- ✅ Container auto-cleanup
- ✅ Read-only task files
- ✅ Limited container lifetime
- ✅ No host system access

## Adding New Backends

To add a new isolation backend:

1. Create a class inheriting from `IsolationBackend`
2. Implement required methods: `setup()`, `execute()`, `cleanup()`, `get_name()`
3. Add to `isolation/__init__.py`
4. Update `run_ada.py` to support it

See `isolation/backend.py` for the interface definition.
