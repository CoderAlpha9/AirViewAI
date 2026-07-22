$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$StateFile = Join-Path $Root ".demo-processes.json"

if (-not (Test-Path $StateFile)) {
    Write-Host "No AirView demo state file was found."
    exit 0
}

$State = Get-Content $StateFile -Raw | ConvertFrom-Json
$Ids = @(
    $State.backend_parent_pid,
    $State.frontend_parent_pid,
    $State.backend_listener_pids,
    $State.frontend_listener_pids
) | ForEach-Object { $_ } | Where-Object { $_ } | Select-Object -Unique

foreach ($Id in $Ids) {
    $Process = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $Id -Force
        Write-Host "Stopped AirView demo process $Id ($($Process.ProcessName))."
    }
}

Remove-Item $StateFile -Force
Write-Host "AirView demo stopped."
