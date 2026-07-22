param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Missing .venv. Run .\scripts\bootstrap.ps1 first." }

$env:AIRVIEW_API_PORT = "$BackendPort"
$env:AIRVIEW_CORS_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
$Arguments = @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "$BackendPort")
if ($Reload) { $Arguments += "--reload" }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "AirView backend exited with code $LASTEXITCODE." }
