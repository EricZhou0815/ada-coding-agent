#!/bin/bash
# Stop all Ada services

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Ada AI Agent..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to stop a service by PID file
stop_service() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo -e "${GREEN}✓ Stopped $name (PID: $pid)${NC}"
        else
            echo -e "${YELLOW}⚠ $name not running${NC}"
        fi
        rm -f "$pid_file"
    fi
}

# Stop services
stop_service "API Server" ".ada-api.pid"
stop_service "Celery Worker" ".ada-worker.pid"
stop_service "Web UI" ".ada-ui.pid"
stop_service "Redis" ".ada-redis.pid"

# Additional cleanup - kill by process name
if command -v pkill >/dev/null 2>&1; then
    pkill -f "uvicorn api.main:app" 2>/dev/null || true
    pkill -f "celery -A worker.tasks" 2>/dev/null || true
fi

# On Windows, stop Redis if it's running
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    taskkill //F //IM redis-server.exe 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}✓ All services stopped${NC}"
