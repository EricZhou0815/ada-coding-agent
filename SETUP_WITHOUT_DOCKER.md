# Running Ada Without Docker

This guide explains how to run the entire Ada application stack on Windows without Docker.

## Quick Start (Automated)

**Want to skip manual setup?** Use the automated startup scripts:

```bash
# Bash (Git Bash/WSL/Linux/Mac)
./start-local.sh

# PowerShell (Windows)
.\start-local.ps1
```

These scripts automatically:
- ✅ Check and create virtual environment
- ✅ Initialize SQLite database
- ✅ Start Redis
- ✅ Launch API server, Celery worker, and UI
- ✅ Save logs to `logs/` directory

**To stop everything:**
```bash
./stop-local.sh    # Bash
.\stop-local.ps1   # PowerShell
```

> **Note**: First-time users should still follow the prerequisites section below to install Python, Node.js, and download Redis.

---

## Architecture Overview

Ada consists of 4-5 main components:
1. **Database** - Data persistence (SQLite or PostgreSQL)
2. **Redis** - Message broker and log streaming
3. **FastAPI Server** - REST API and webhook handling
4. **Celery Worker** - Background task execution
5. **Next.js UI** - Web console (optional)

> **Note**: SQLite is the **default database** and requires zero setup! Use PostgreSQL only if you need production-grade concurrency or multi-instance deployments.

---

## Prerequisites

### Required Software

1. **Python 3.11+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Ensure "Add to PATH" is checked during installation

2. **Node.js 20+** (for UI)
   - Download from [nodejs.org](https://nodejs.org/)

3. **PostgreSQL 16** (OPTIONAL - only if you need production-grade database)
   - Download from [postgresql.org](https://www.postgresql.org/download/windows/)
   - During installation, remember your postgres password
   - **Skip this if using SQLite** (default, recommended for local development)

4. **Redis** (Windows compatible version)
   - Option A: [Memurai](https://www.memurai.com/) (Redis-compatible for Windows)
   - Option B: [Redis for Windows](https://github.com/tporadowski/redis/releases) (community port)

---
Choose Your Database

### Option A: SQLite (Recommended for Local Development)

**✅ No installation required!** SQLite is the default and will automatically create a database file when you first run Ada.

**Advantages**:
- Zero configuration
- No separate service to manage
- Perfect for single-instance deployments
- Sufficient for most development and small-scale production use

**Skip to Step 2** if using SQLite.

---

### Option B: PostgreSQL (For Production/Multi-Instance)

Only use PostgreSQL if you need:
- Multiple API instances accessing the same database
- High concurrency (100+ concurrent requests)
- Advanced query optimization

#### 1.1 Create Database and User

Open **SQL Shell (psql)** from the Start menu and run:

```sql
CREATE DATABASE ada_db;
CREATE USER ada_user WITH PASSWORD 'ada_password';
GRANT ALL PRIVILEGES ON DATABASE ada_db TO ada_user;
\q
```

#
### 1.2 Verify Connection

Test the connection:

```powershell
psql -U ada_user -d ada_db
# Enter password when prompted: ada_password
# If successful, you'll see: ada_db=>
\q
```

---

## Step 2: Install and Start Redis

### Using Memurai (Recommended)

1. Download and install [Memurai](https://www.memurai.com/get-memurai)
2. Start Memurai from the Start menu or:
   ```powershell
   net start Memurai
   ```

### Using Redis for Windows

1. Download from [Redis Windows releases](https://github.com/tporadowski/redis/releases)
2. Extract to `C:\Redis`
3. Start Redis server:
   ```powershell
   cd C:\Redis
   .\redis-server.exe
   ```

### Verify Redis is Running

```powershell
# In a new terminal
redis-cli ping
# Should return: PONG
```

---

## Step 3: Set Up Python Environment

### 3.1 Create Virtual Environment

```powershell
cd c:\Users\cnwez2\ezhou\projects\ada-coding-agent
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If you get an execution policy error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

### 3.2 Install Python Dependencies

```powershell
pip install -r requirements.txt
```

---

## Step 4: Configure Environment Variables
Configuration
# Option A: SQLite (default - no setup required, just omit DATABASE_URL)
# The database file will be created automatically as 'ada_jobs.db'

# Option B: PostgreSQL (uncomment if you installed PostgreSQL)
# ### 4.1 Create .env File

```powershell
cp env.example .env
```

### 4.2 Edit .env File

Open `.env` in your editor and configure:

```

> **Note**: With SQLite, this automatically creates `ada_jobs.db` in your project root. With PostgreSQL, it creates the tables in your configured database.bash
# LLM Provider (choose one)
GROQ_API_KEY=gsk_your_actual_groq_key_here
# OR
OPENAI_API_KEY=sk_your_actual_openai_key_here

# GitHub Integration (required for SDLC features)
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Database (local PostgreSQL)
DATABASE_URL=postgresql://ada_user:ada_password@localhost:5432/ada_db

# Redis (local)
REDIS_URL=redis://localhost:6379/0

# VCS Platform
VCS_PLATFORM=github
```

### 4.3 Initialize Database

```powershell
# Ensure virtual environment is activated
python -c "from api.database import init_db; init_db()"
```

---

## Step 5: Run the Application

You need to run **3 separate terminal windows** (all with virtual environment activated):

### Terminal 1: FastAPI Server

```powershell
cd c:\Users\cnwez2\ezhou\projects\ada-coding-agent
.\venv\Scripts\Activate.ps1
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at: **http://localhost:8000**

API documentation: **http://localhost:8000/docs**

### Terminal 2: Celery Worker

```powershell
cd c:\Users\cnwez2\ezhou\projects\ada-coding-agent
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
celery -A worker.tasks worker --loglevel=info --pool=solo
```

> **Note**: Windows requires `--pool=solo` flag for Celery workers. Setting `PYTHONPATH` ensures imports work correctly.

### Terminal 3: Next.js UI (Optional)

```powershell
cd c:\Users\cnwez2\ezhou\projects\ada-coding-agent\ui
npm install
npm run dev
```

The UI will be available at: **http://localhost:3000**

---

## Step 6: Verify Everything is Working

### 6.1 Check Health Endpoint

```powershell
curl http://localhost:8000/health
```

Should return:
```json
{"status":"healthy"}
```

### 6.2 Test Story Execution

Create a test file `test_story.json`:

```json
{
  "title": "Test Story",
  "description": "Create a simple hello.py file that prints 'Hello Ada'",
  "acceptance_criteria": [
    "File hello.py exists",
    "Prints 'Hello Ada' when run"
  ],
  "repo_url": "https://github.com/your-username/test-repo",
  "base_branch": "main"
}
```

Submit the story:

```powershell
curl -X POST http://localhost:8000/api/v1/execute `
  -H "Content-Type: application/json" `
  -d "@test_story.json"
```

Watch the logs in Terminal 2 (Celery Worker) to see Ada processing the story.

---

## Common Issues and Solutions

### PostgreSQL Connection Failed

**Error**: `could not connect to server`

**Solution**:
1. Ensure PostgreSQL service is running:
   ```powershell
   Get-Service postgresql*
   Start-Service postgresql-x64-16  # Replace with your service name
   ```

2. Verify connection settings in `.env` match your PostgreSQL configuration

### Redis Connection Failed

**Error**: `Error connecting to Redis`

**Solution**:
1. Ensure Redis/Memurai is running:
   ```powershell
   Get-Service Memurai
   Start-Service Memurai
   ```
   Or manually start `redis-server.exe`

### Celery Worker Won't Start

**Error**: `ValueError: not enough values to unpack`

**Solution**: Add `--pool=solo` flag (Windows requirement):
```powershell
celery -A worker.tasks worker --loglevel=info --pool=solo
```

### Port Already in Use

**Error**: `Address already in use`

**Solution**: Find and kill the process using the port:
```powershell
# Find PID using port 8000
netstat -ano | findstr :8000
# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'xyz'`

**Solution**: Ensure virtual environment is activated and dependencies installed:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Running Specific Ada Tools

### Run Single Story (Without API/Worker)

For simple local testing without the full stack:

```powershell
python run_ada.py
```

### Run SDLC Orchestrator

Process a full user story with PR creation:

```powershell
python run_sdlc.py
```

### Run Epic Mode

Process multiple stories from a backlog:

```powershell
python run_epic.py
```

### Run Planning Agent

Interactive requirement clarification:

```powershell
python run_demo.py
```

---

## Stopping the Application

### Stop All Services

1. Press `Ctrl+C` in each terminal window (API, Worker, UI)
2. Stop PostgreSQL (optional):
   ```powershell
   Stop-Service postgresql-x64-16
   ```
3. Stop Redis/Memurai (optional):
   ```powershell
   Stop-Service Memurai
   ```

### Deactivate Virtual Environment

```powershell
deactivate
```

---

## Production Considerations

For production deployment without Docker:

1. **Use a Process Manager**:
   - Install `pm2` for Node.js apps:
     ```powershell
     npm install -g pm2
     pm2 start "uvicorn api.main:app --host 0.0.0.0 --port 8000" --name ada-api
     pm2 start "celery -A worker.tasks worker --pool - **SKIP if using SQLite**=solo" --name ada-worker
     ```

2. **Configure PostgreSQL for Production**:
   - Edit `postgresql.conf` for performance tuning
   - Set up regular backups
   - Use SSL connections

3. **Secure Redis**:
   - Enable password authentication
   - Bind to localhost only (or use firewall)

4. **Set Up Reverse Proxy**:
   - Use IIS or nginx for Windows to proxy requests to FastAPI

5. **Configure Logging**:
   - Set up file-based logging instead of console output
   - Configure log rotation

---

## Quick Reference

### Component Checklist

Before running Ada, ensure these are running:

- [ ] PostgreSQL service (`Get-Service postgresql*`)
- [ ] Redis/Memurai service (`Get-Service Memurai` or `redis-server.exe`)
- [ ] Python virtual environment activated (`.\venv\Scripts\Activate.ps1`)
- [ ] `.env` file configured with API keys

### Essential Commands

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Start API server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker
celery -A worker.tasks worker --loglevel=info --pool=solo

# Start UI
cd ui; npm run dev

# Check service status
Get-Service postgresql*, Memurai

# Test connectivity
redis-cli ping
psql -U ada_user -d ada_db -c "SELECT 1"
curl http://localhost:8000/health
```

---

## Next Steps

- Read [docs/PLANNING_AGENT.md](docs/PLANNING_AGENT.md) for planning features
- Read [docs/WEBHOOK_SETUP.md](docs/WEBHOOK_SETUP.md) for CI/CD integration
- Read [docs/MULTI_INSTANCE_DEPLOYMENT.md](docs/MULTI_INSTANCE_DEPLOYMENT.md) for scaling

---

**Need help?** Check the main [README.md](README.md) or open an issue on GitHub.
