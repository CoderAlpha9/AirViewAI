param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Frontend = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    throw "Missing frontend dependencies. Run .\scripts\bootstrap.ps1 first."
}

$env:VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort/api"
& npm.cmd --prefix $Frontend run dev -- "--host" "127.0.0.1" "--port" "$FrontendPort"
if ($LASTEXITCODE -ne 0) { throw "AirView frontend exited with code $LASTEXITCODE." }
