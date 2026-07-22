param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [switch]$ForceRestartDemoProcesses
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$StateFile = Join-Path $Root ".demo-processes.json"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Frontend = Join-Path $Root "frontend"

function Assert-PathExists {
    param([string]$Path, [string]$Message)
    if (-not (Test-Path $Path)) { throw $Message }
}

function Assert-PortFree {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($Listener) { throw "Port $Port is already occupied. Choose another port or stop the owning application." }
}

Assert-PathExists $Python "Missing .venv. Run .\scripts\bootstrap.ps1 once, then retry."
Assert-PathExists (Join-Path $Frontend "node_modules") "Missing frontend dependencies. Run npm --prefix frontend install, then retry."
foreach ($Relative in @(
    "models\forecasting\global_residual\pm2_5\24\model.joblib",
    "models\forecasting\global_residual\pm2_5\48\model.joblib",
    "models\forecasting\global_residual\pm2_5\72\model.joblib",
    "models\forecasting\global_residual\pm10\24\model.joblib",
    "models\forecasting\global_residual\pm10\48\model.joblib",
    "models\forecasting\global_residual\pm10\72\model.joblib"
)) {
    Assert-PathExists (Join-Path $Root $Relative) "Missing required AirView artifact: $Relative"
}

if (Test-Path $StateFile) {
    if (-not $ForceRestartDemoProcesses) {
        throw "A demo state file already exists. Run .\scripts\stop_demo.ps1 or pass -ForceRestartDemoProcesses."
    }
    & (Join-Path $PSScriptRoot "stop_demo.ps1")
}

Assert-PortFree $BackendPort
Assert-PortFree $FrontendPort

if (-not $SkipBuild) {
    & npm --prefix $Frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
}

$BackendOutLog = Join-Path $Root "outputs\logs\backend-demo.out.log"
$BackendErrLog = Join-Path $Root "outputs\logs\backend-demo.err.log"
$FrontendOutLog = Join-Path $Root "outputs\logs\frontend-demo.out.log"
$FrontendErrLog = Join-Path $Root "outputs\logs\frontend-demo.err.log"
New-Item -ItemType Directory -Force (Split-Path $BackendOutLog -Parent) | Out-Null

$PreviousApiPort = $env:AIRVIEW_API_PORT
$PreviousCorsOrigins = $env:AIRVIEW_CORS_ORIGINS
try {
    $env:AIRVIEW_API_PORT = "$BackendPort"
    $env:AIRVIEW_CORS_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
    $Backend = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
        -WorkingDirectory (Join-Path $Root "backend") `
        -RedirectStandardOutput $BackendOutLog `
        -RedirectStandardError $BackendErrLog `
        -WindowStyle Hidden `
        -PassThru
}
finally {
    if ($null -eq $PreviousApiPort) { Remove-Item Env:AIRVIEW_API_PORT -ErrorAction SilentlyContinue } else { $env:AIRVIEW_API_PORT = $PreviousApiPort }
    if ($null -eq $PreviousCorsOrigins) { Remove-Item Env:AIRVIEW_CORS_ORIGINS -ErrorAction SilentlyContinue } else { $env:AIRVIEW_CORS_ORIGINS = $PreviousCorsOrigins }
}

$FrontendCommand = "set VITE_API_BASE_URL=http://127.0.0.1:$BackendPort/api&& npm.cmd --prefix `"$Frontend`" run dev -- --host 127.0.0.1 --port $FrontendPort"
$FrontendProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", $FrontendCommand) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $FrontendOutLog `
    -RedirectStandardError $FrontendErrLog `
    -WindowStyle Hidden `
    -PassThru

$Ready = $false
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    try {
        $Health = Invoke-WebRequest "http://127.0.0.1:$BackendPort/api/health" -UseBasicParsing -TimeoutSec 2
        $FrontendHealth = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 2
        if ($Health.StatusCode -eq 200 -and $FrontendHealth.StatusCode -eq 200) {
            $Ready = $true
            break
        }
    }
    catch { Start-Sleep -Milliseconds 500 }
}

if (-not $Ready) {
    if (Get-Process -Id $Backend.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $Backend.Id -Force }
    if (Get-Process -Id $FrontendProcess.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $FrontendProcess.Id -Force }
    throw "AirView services did not become ready. Review outputs\logs\backend-demo.err.log and frontend-demo.err.log."
}

$BackendOwners = @(Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
$FrontendOwners = @(Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
$State = @{
    backend_parent_pid = $Backend.Id
    frontend_parent_pid = $FrontendProcess.Id
    backend_listener_pids = $BackendOwners
    frontend_listener_pids = $FrontendOwners
    backend_port = $BackendPort
    frontend_port = $FrontendPort
    started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$State | ConvertTo-Json -Depth 4 | Set-Content $StateFile -Encoding UTF8

Write-Host ""
Write-Host "AirView AI is ready." -ForegroundColor Green
Write-Host "Dashboard : http://127.0.0.1:$FrontendPort/"
Write-Host "API       : http://127.0.0.1:$BackendPort/api"
Write-Host "API docs  : http://127.0.0.1:$BackendPort/docs"
Write-Host "Verify    : powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_demo.ps1 -BackendPort $BackendPort -FrontendPort $FrontendPort"
Write-Host "Stop      : powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_demo.ps1"

try {
    $OperationalStatus = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/operations/status" -TimeoutSec 10
    $UnavailableOptional = @($OperationalStatus.providers.PSObject.Properties | Where-Object { $_.Value -eq "not_configured" } | ForEach-Object { $_.Name })
    if ($UnavailableOptional.Count) {
        Write-Host "Optional providers without credentials: $($UnavailableOptional -join ', '). Their panels degrade gracefully." -ForegroundColor Yellow
    }
}
catch {
    Write-Host "Provider configuration summary is still loading; the dashboard remains available and reports provider state per panel." -ForegroundColor Yellow
}

if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort/" }
