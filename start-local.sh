#!/bin/bash
# Start Ada locally without Docker

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Ada AI Agent (Local Mode)"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    if command_exists lsof; then
        lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
    elif command_exists netstat; then
        netstat -an | grep ":$1 " | grep LISTEN >/dev/null 2>&1
    else
        return 1
    fi
}

# 1. Check prerequisites
echo -e "${CYAN}Checking prerequisites...${NC}"

if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment not found. Creating...${NC}"
    python -m venv venv
fi

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env file not found. Please copy env.example to .env and configure it.${NC}"
    exit 1
fi

# 2. Activate virtual environment
echo -e "${CYAN}Activating virtual environment...${NC}"
source venv/bin/activate || source venv/Scripts/activate

# 3. Check if database is initialized
if [ ! -f "ada_jobs.db" ]; then
    echo -e "${CYAN}Initializing SQLite database...${NC}"
    python -c "from api.database import init_db; init_db()"
    echo -e "${GREEN}✓ Database initialized${NC}"
fi

# 4. Start Redis
echo ""
echo -e "${CYAN}Starting Redis...${NC}"
if port_in_use 6379; then
    echo -e "${GREEN}✓ Redis already running on port 6379${NC}"
else
    # Check different possible Redis locations
    if [ -f "/c/Redis/redis-server.exe" ]; then
        # Windows (Git Bash)
        /c/Redis/redis-server.exe &
        REDIS_PID=$!
        echo -e "${GREEN}✓ Redis started (PID: $REDIS_PID)${NC}"
    elif command_exists redis-server; then
        # Linux/Mac
        redis-server --daemonize yes
        echo -e "${GREEN}✓ Redis started as daemon${NC}"
    else
        echo -e "${YELLOW}⚠ Redis not found. Please install Redis or download to C:\\Redis${NC}"
        echo -e "${YELLOW}  Download: https://github.com/tporadowski/redis/releases${NC}"
        exit 1
    fi
    sleep 2
fi

# 5. Start API Server
echo ""
echo -e "${CYAN}Starting API Server...${NC}"
if port_in_use 8000; then
    echo -e "${YELLOW}⚠ Port 8000 already in use${NC}"
else
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > logs/api.log 2>&1 &
    API_PID=$!
    echo -e "${GREEN}✓ API Server started (PID: $API_PID)${NC}"
    echo "  Logs: logs/api.log"
fi

# 6. Start Celery Worker
echo ""
echo -e "${CYAN}Starting Celery Worker...${NC}"
mkdir -p logs
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    celery -A worker.tasks worker --loglevel=info --pool=solo > logs/worker.log 2>&1 &
else
    # Linux/Mac
    celery -A worker.tasks worker --loglevel=info > logs/worker.log 2>&1 &
fi
WORKER_PID=$!
echo -e "${GREEN}✓ Celery Worker started (PID: $WORKER_PID)${NC}"
echo "  Logs: logs/worker.log"

# 7. Start UI (optional)
echo ""
if [ -d "ui/node_modules" ]; then
    echo -e "${CYAN}Starting Web UI...${NC}"
    if port_in_use 3000; then
        echo -e "${YELLOW}⚠ Port 3000 already in use${NC}"
    else
        cd ui
        npm run dev > ../logs/ui.log 2>&1 &
        UI_PID=$!
        cd ..
        echo -e "${GREEN}✓ Web UI started (PID: $UI_PID)${NC}"
        echo "  Logs: logs/ui.log"
    fi
else
    echo -e "${YELLOW}⚠ Web UI dependencies not found. Run: cd ui && npm install${NC}"
fi

# 8. Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✓ Ada is running!${NC}"
echo ""
echo -e "${CYAN}Access Points:${NC}"
echo "  API:      http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Web UI:   http://localhost:3000"
echo ""
echo -e "${CYAN}Logs:${NC}"
echo "  API:    tail -f logs/api.log"
echo "  Worker: tail -f logs/worker.log"
echo "  UI:     tail -f logs/ui.log"
echo ""
echo -e "${YELLOW}To stop all services:${NC}"
echo "  ./stop-local.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Save PIDs for cleanup
echo "$API_PID" > .ada-api.pid
echo "$WORKER_PID" > .ada-worker.pid
[ ! -z "$UI_PID" ] && echo "$UI_PID" > .ada-ui.pid
[ ! -z "$REDIS_PID" ] && echo "$REDIS_PID" > .ada-redis.pid
