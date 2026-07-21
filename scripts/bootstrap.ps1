param(
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot

function Assert-NativeCommandSucceeded {
    param([string]$CommandName)

    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed with exit code $LASTEXITCODE."
    }
}

if (-not $SkipBackend) {
    $VirtualEnvironment = Join-Path $RepositoryRoot ".venv"
    py -3.13 -m venv $VirtualEnvironment
    Assert-NativeCommandSucceeded "Python virtual environment creation"
    & (Join-Path $VirtualEnvironment "Scripts\python.exe") -m pip install --upgrade pip
    Assert-NativeCommandSucceeded "pip upgrade"
    & (Join-Path $VirtualEnvironment "Scripts\python.exe") -m pip install -r (Join-Path $RepositoryRoot "backend\requirements.txt")
    Assert-NativeCommandSucceeded "Backend dependency installation"
    & (Join-Path $VirtualEnvironment "Scripts\python.exe") -m pip install -e (Join-Path $RepositoryRoot "ml")
    Assert-NativeCommandSucceeded "ML package installation"
}

if (-not $SkipFrontend) {
    Push-Location (Join-Path $RepositoryRoot "frontend")
    try {
        npm install
        Assert-NativeCommandSucceeded "Frontend dependency installation"
    }
    finally {
        Pop-Location
    }
}

Write-Host "AirView AI dependencies are installed."
