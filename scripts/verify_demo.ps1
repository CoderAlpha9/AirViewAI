param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$script:Checks = @()

function Test-AirViewEndpoint {
    param([string]$Name, [string]$Url)
    $Watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $Response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 45
        $script:Checks += @{
            name = $Name
            url = $Url
            status = $Response.StatusCode
            bytes = $Response.RawContentLength
            duration_ms = $Watch.ElapsedMilliseconds
            passed = ($Response.StatusCode -eq 200)
        }
    }
    catch {
        $script:Checks += @{
            name = $Name
            url = $Url
            status = 0
            bytes = 0
            duration_ms = $Watch.ElapsedMilliseconds
            passed = $false
            error = $_.Exception.Message
        }
    }
}

$Api = "http://127.0.0.1:$BackendPort/api"
Test-AirViewEndpoint "backend-health" "$Api/health"
Test-AirViewEndpoint "operations-status" "$Api/operations/status"
Test-AirViewEndpoint "city-registry" "$Api/operations/cities"
Test-AirViewEndpoint "five-city-comparison" "$Api/operations/network?mode=demo"

foreach ($City in @("delhi-ncr", "agra", "amritsar", "lucknow", "ludhiana")) {
    Test-AirViewEndpoint "dashboard-$City" "$Api/operations/dashboard?city_id=$City&pollutant=pm2_5&horizon=72&language=en&mode=demo"
}

Test-AirViewEndpoint "frontend-dashboard" "http://127.0.0.1:$FrontendPort/"
Test-AirViewEndpoint "frontend-dashboard-alias" "http://127.0.0.1:$FrontendPort/dashboard"

$Passed = @($Checks | Where-Object { $_.passed }).Count
$Failed = @($Checks | Where-Object { -not $_.passed }).Count
$Report = @{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    backend_port = $BackendPort
    frontend_port = $FrontendPort
    passed = $Passed
    failed = $Failed
    checks = $Checks
}
$ReportPath = Join-Path $Root "outputs\reports\demo_verification_report.json"
$Report | ConvertTo-Json -Depth 6 | Set-Content $ReportPath -Encoding UTF8

Write-Host "AirView verification: $Passed passed, $Failed failed."
$Checks | ForEach-Object {
    $Mark = if ($_.passed) { "PASS" } else { "FAIL" }
    Write-Host ("{0,-5} {1,-28} HTTP {2} ({3} ms)" -f $Mark, $_.name, $_.status, $_.duration_ms)
}
if ($Failed -gt 0) { exit 1 }
