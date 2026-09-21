# MCP - Ollama - LangChain Agent -- Windows start script
# Clone the repo, then run: .\scripts\start.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Join-Path $PSScriptRoot ".."
Set-Location $ProjectRoot

Write-Host ""
Write-Host "=== MCP - Ollama - LangChain Agent ===" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Python environment
# ---------------------------------------------------------------------------

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python is not installed. Download from https://python.org" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "[..] Creating virtual environment..."
    python -m venv .venv
}

. .venv\Scripts\Activate.ps1

Write-Host "[..] Installing dependencies..."
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pip install failed. See above for details." -ForegroundColor Red
    exit 1
}
Write-Host "[ok] Dependencies ready" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Ollama
# ---------------------------------------------------------------------------

# Refresh PATH so a just-installed Ollama is visible without reopening the terminal
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH", "User")

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Ollama is not installed." -ForegroundColor Red
    Write-Host "        Download it from: https://ollama.com/download/windows"
    Write-Host "        Then re-run this script."
    exit 1
}

# Start Ollama serve if not already running
try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
    Write-Host "[ok] Ollama already running" -ForegroundColor Green
} catch {
    Write-Host "[..] Starting Ollama..."
    Start-Process ollama -ArgumentList "serve" -NoNewWindow
    Start-Sleep -Seconds 3
}

# Pull models if not already present
$pulledModels = (ollama list 2>$null) -join " "

foreach ($model in @("qwen2.5:3b", "nomic-embed-text")) {
    if ($pulledModels -notmatch $model) {
        Write-Host "[..] Pulling $model (first run, this may take a while)..." -ForegroundColor Yellow
        ollama pull $model
    } else {
        Write-Host "[ok] $model already pulled" -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# 3. Start services
# ---------------------------------------------------------------------------

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "[..] Starting MCP server on :8001"
$mcp = Start-Process $python -ArgumentList "-m", "mcp_server.main" -PassThru -NoNewWindow -WorkingDirectory $ProjectRoot

Start-Sleep -Seconds 2

Write-Host "[..] Starting Agent API on :8000"
$agent = Start-Process $python -ArgumentList "-m", "agent.main" -PassThru -NoNewWindow -WorkingDirectory $ProjectRoot

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "All services running" -ForegroundColor Green
Write-Host "  Chat UI     -> http://localhost:8000"
Write-Host "  Agent API   -> http://localhost:8000/docs"
Write-Host "  MCP server  -> http://localhost:8001/health"
Write-Host ""
Write-Host "Press Ctrl+C to stop"

try {
    Wait-Process -Id $mcp.Id, $agent.Id
} finally {
    Write-Host "`nStopping..." -ForegroundColor Yellow
    Stop-Process -Id $mcp.Id, $agent.Id -Force -ErrorAction SilentlyContinue
}
