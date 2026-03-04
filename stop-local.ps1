# Stop all Ada services (PowerShell version)

$PROJECT_DIR = $PSScriptRoot
Write-Host "Stopping Ada AI Agent..." -ForegroundColor Yellow
Write-Host ""

$stopped = 0

# Stop Redis
$redisProcess = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
if ($redisProcess) {
    Stop-Process -Name "redis-server" -Force
    Write-Host "Stopped Redis" -ForegroundColor Green
    $stopped++
}

# Stop Python processes from this project (API Server & Celery Worker)
$pythonProcesses = Get-Process -Name "python", "python3.12" -ErrorAction SilentlyContinue
foreach ($proc in $pythonProcesses) {
    if ($proc.Path -like "*$PROJECT_DIR*") {
        Stop-Process -Id $proc.Id -Force
        Write-Host "Stopped Python process - PID: $($proc.Id)" -ForegroundColor Green
        $stopped++
    }
}

# Stop Node processes from ui directory (Web UI)
$nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    # Check if any are from the UI directory by looking at window titles or just stop all
    # Safer approach: stop all node processes during development
    foreach ($proc in $nodeProcesses) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped Node process - PID: $($proc.Id)" -ForegroundColor Green
        $stopped++
    }
}

Write-Host ""
if ($stopped -gt 0) {
    Write-Host "Stopped $stopped process(es)" -ForegroundColor Green
} else {
    Write-Host "No Ada services were running" -ForegroundColor Yellow
}
Write-Host "All Ada services stopped" -ForegroundColor Green
