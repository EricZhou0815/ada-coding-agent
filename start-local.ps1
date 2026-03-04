# Start Ada locally without Docker (PowerShell version)

$ErrorActionPreference = "Stop"
$PROJECT_DIR = $PSScriptRoot
Set-Location $PROJECT_DIR

Write-Host "Starting Ada AI Agent (Local Mode)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv .venv
}

if (-not (Test-Path ".env")) {
    Write-Host ".env file not found. Please copy env.example to .env and configure it." -ForegroundColor Yellow
    exit 1
}

# 2. Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

# 3. Check if database is initialized
if (-not (Test-Path "ada_jobs.db")) {
    Write-Host "Initializing SQLite database..." -ForegroundColor Cyan
    python -c "from api.database import init_db; init_db()"
    Write-Host "Database initialized" -ForegroundColor Green
}

# 4. Start Redis
Write-Host ""
Write-Host "Starting Redis..." -ForegroundColor Cyan
$redisProcess = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
if ($redisProcess) {
    Write-Host "Redis already running (PID: $($redisProcess.Id))" -ForegroundColor Green
} else {
    if (Test-Path "C:\Redis\redis-server.exe") {
        Start-Process -FilePath "C:\Redis\redis-server.exe" -WorkingDirectory "C:\Redis"
        Start-Sleep -Seconds 2
        Write-Host "Redis started" -ForegroundColor Green
    } else {
        Write-Host "Redis not found at C:\Redis. Please download Redis:" -ForegroundColor Yellow
        Write-Host "  https://github.com/tporadowski/redis/releases" -ForegroundColor Yellow
        exit 1
    }
}

# 5. Create logs directory
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

# 6. Start API Server
Write-Host ""
Write-Host "Starting API Server..." -ForegroundColor Cyan
$apiPort = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($apiPort) {
    Write-Host "Port 8000 already in use" -ForegroundColor Yellow
} else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; .\.venv\Scripts\Activate.ps1; uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal
    Write-Host "API Server started in new window" -ForegroundColor Green
}

# 7. Start Celery Worker
Write-Host ""
Write-Host "Starting Celery Worker..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; .\.venv\Scripts\Activate.ps1; celery -A worker.tasks worker --loglevel=info --pool=solo" -WindowStyle Normal
Write-Host "Celery Worker started in new window" -ForegroundColor Green

# 8. Start UI (optional)
Write-Host ""
if (Test-Path "ui\node_modules") {
    Write-Host "Starting Web UI..." -ForegroundColor Cyan
    $uiPort = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
    if ($uiPort) {
        Write-Host "Port 3000 already in use" -ForegroundColor Yellow
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR\ui'; npm run dev" -WindowStyle Normal
        Write-Host "Web UI started in new window" -ForegroundColor Green
    }
} else {
    Write-Host "Web UI dependencies not found. Run: cd ui && npm install" -ForegroundColor Yellow
}

# 9. Summary
Write-Host ""
Write-Host "=========================================" -ForegroundColor Gray
Write-Host "Ada is running!" -ForegroundColor Green
Write-Host ""
Write-Host "Access Points:" -ForegroundColor Cyan
Write-Host "  API:      http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Web UI:   http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "To stop all services:" -ForegroundColor Yellow
Write-Host "  1. Close all terminal windows" -ForegroundColor Gray
Write-Host "  2. Run: .\stop-local.ps1" -ForegroundColor Gray
Write-Host "=========================================" -ForegroundColor Gray
