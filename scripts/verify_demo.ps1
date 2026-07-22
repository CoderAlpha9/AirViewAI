param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$script:Checks = @()

function Add-Check {
    param([string]$Name, [string]$Url, [int]$Status, [long]$Duration, [bool]$Passed, [string]$Message = "")
    $script:Checks += [ordered]@{
        name = $Name
        url = $Url
        status = $Status
        duration_ms = $Duration
        passed = $Passed
        message = $Message
    }
}

function Test-JsonEndpoint {
    param([string]$Name, [string]$Url, [scriptblock]$Validate)
    $Watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $Response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 90
        $Payload = $Response.Content | ConvertFrom-Json
        $Valid = if ($Validate) { [bool](& $Validate $Payload) } else { $true }
        Add-Check $Name $Url $Response.StatusCode $Watch.ElapsedMilliseconds ($Response.StatusCode -eq 200 -and $Valid) $(if ($Valid) { "" } else { "Response validation failed" })
        return $Payload
    }
    catch {
        Add-Check $Name $Url 0 $Watch.ElapsedMilliseconds $false "Request or response validation failed"
        return $null
    }
}

function Test-HtmlEndpoint {
    param([string]$Name, [string]$Url)
    $Watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $Response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 15
        $Valid = $Response.StatusCode -eq 200 -and $Response.Content -match '<div id="root"></div>'
        Add-Check $Name $Url $Response.StatusCode $Watch.ElapsedMilliseconds $Valid $(if ($Valid) { "" } else { "Frontend shell was not returned" })
    }
    catch {
        Add-Check $Name $Url 0 $Watch.ElapsedMilliseconds $false "Frontend was unreachable"
    }
}

$Api = "http://127.0.0.1:$BackendPort/api"
$null = Test-JsonEndpoint "backend-health" "$Api/health" { param($p) $p.status -eq "ok" }
$null = Test-JsonEndpoint "copilot-status" "$Api/copilot/status" {
    param($p) $p.provider -eq "Google Gemini" -and $p.model -and $null -ne $p.enabled -and $null -ne $p.configured
}
$null = Test-JsonEndpoint "operations-status" "$Api/operations/status" { param($p) $p.status -eq "ready" }
$null = Test-JsonEndpoint "operational-city-registry" "$Api/operations/cities" { param($p) $p.count -eq 5 }
$Network = Test-JsonEndpoint "five-city-outlook" "$Api/operations/network" {
    param($p)
    $Invalid = @($p.cities | Where-Object { $_.pollutant -ne "pm2_5" -or $_.horizon -ne 24 -or $_.mode -ne "fixed_next_24h_pm2_5_outlook" -or ($null -ne $_.value_24h -and (-not $_.snapshot_id -or -not $_.issue_timestamp -or -not $_.valid_timestamp -or $null -eq $_.aqi -or -not $_.category -or -not $_.colour -or -not $_.priority)) })
    $p.cities.Count -eq 5 -and $p.pollutant -eq "pm2_5" -and $Invalid.Count -eq 0
}

$DefaultCurrents = @{}
$DefaultForecasts = @{}
foreach ($City in @("delhi-ncr", "agra", "amritsar", "lucknow", "ludhiana")) {
    $EncodedCity = [uri]::EscapeDataString($City)
    $DefaultCurrents[$City] = Test-JsonEndpoint "default-city-$City" "$Api/live/current?city=$EncodedCity&pollutant=pm2_5&horizon=24" {
        param($p) $p.context.city.city_id -eq $City -and $p.context.pollutant -eq "pm2_5" -and $p.context.horizon -eq 24
    }
    $DefaultForecasts[$City] = Test-JsonEndpoint "default-city-$City-forecast" "$Api/live/forecast?city=$EncodedCity&pollutant=pm2_5&horizon=24" {
        param($p) $p.context.city.city_id -eq $City -and $p.data.status -in @("available", "unavailable") -and ($p.data.status -eq "unavailable" -or ($p.data.peak -and $p.data.priority))
    }
}
$NetworkMismatches = @($Network.cities | Where-Object {
    $ForecastPanel = $DefaultForecasts[$_.city_id]
    ($null -ne $_.value_24h -and ($null -eq $ForecastPanel -or [math]::Abs([double]$_.value_24h - [double]$ForecastPanel.data.peak.value) -gt 0.01 -or $_.aqi -ne $ForecastPanel.data.peak.aqi -or $_.category -ne $ForecastPanel.data.peak.category -or $_.colour -ne $ForecastPanel.data.peak.colour -or $_.priority -ne $ForecastPanel.data.priority -or $_.snapshot_id -ne $ForecastPanel.context.snapshot_id)) -or ($null -eq $_.value_24h -and $null -ne $ForecastPanel.data.peak)
})
Add-Check "five-city-forecast-consistency" "internal://five-city-forecast" 200 0 ($null -ne $Network -and $NetworkMismatches.Count -eq 0) $(if ($null -ne $Network -and $NetworkMismatches.Count -eq 0) { "" } else { "Five-city value, AQI, category, colour, priority or snapshot did not match the canonical 24-hour forecast" })

$Search = Test-JsonEndpoint "city-search" "$Api/live/cities/search?q=Mysuru" {
    param($p) $p.count -gt 0 -and $p.data[0].city_id -and $p.data[0].bounds.Count -eq 4
}
$DynamicCity = if ($Search -and $Search.data.Count) { $Search.data[0].name } else { "Mysuru" }
$EncodedDynamicCity = [uri]::EscapeDataString($DynamicCity)
$PanelBase = "city=$EncodedDynamicCity&pollutant=pm2_5&horizon=48"

$Current = Test-JsonEndpoint "dynamic-current" "$Api/live/current?$PanelBase" {
    param($p) $p.context.city.name -eq $DynamicCity -and $p.context.pollutant -eq "pm2_5" -and $p.context.horizon -eq 48 -and $p.data.category -and $p.data.colour
}
$Forecast = Test-JsonEndpoint "dynamic-forecast" "$Api/live/forecast?$PanelBase" {
    param($p) $p.data.status -eq "available" -and $p.data.points.Count -eq 48 -and $p.data.priority
}
$Stations = Test-JsonEndpoint "dynamic-stations" "$Api/live/stations?$PanelBase" {
    param($p) $p.data.available_count -ge 0 -and $p.data.selected_count -ge 0 -and $null -ne $p.data.stations
}
$Map = Test-JsonEndpoint "dynamic-grid-map" "$Api/live/map?$PanelBase&max_cells=400" {
    param($p)
    $CurrentValues = @($p.data.features | ForEach-Object { $_.properties.current } | Where-Object { $null -ne $_ } | Select-Object -Unique)
    $ForecastValues = @($p.data.features | ForEach-Object { $_.properties.forecast } | Where-Object { $null -ne $_ } | Select-Object -Unique)
    $Legend = @{}; $p.data.metadata.category_legend | ForEach-Object { $Legend[$_.category] = $_.colour }
    $BadColours = @($p.data.features | Where-Object { $_.properties.category -and $Legend[$_.properties.category] -ne $_.properties.colour })
    $p.data.type -eq "FeatureCollection" -and $p.data.metadata.layer_kind -eq "current" -and $p.data.features.Count -gt 1 -and $CurrentValues.Count -gt 1 -and $ForecastValues.Count -gt 1 -and $Legend.Count -eq 6 -and $BadColours.Count -eq 0
}
$Intelligence = Test-JsonEndpoint "dynamic-source-intelligence" "$Api/live/source-intelligence?$PanelBase" {
    param($p) $p.data.priority -and $p.data.confidence -ge 0 -and $p.data.confidence -le 1
}
$Actions = Test-JsonEndpoint "dynamic-actions" "$Api/live/actions?$PanelBase" {
    param($p) $null -ne $p.data
}
$Advisory = Test-JsonEndpoint "dynamic-advisory" "$Api/live/advisory?$PanelBase" {
    param($p) $p.data.status -in @("available", "unavailable")
}
$Snapshot = Test-JsonEndpoint "dynamic-dashboard-snapshot" "$Api/live/snapshot?$PanelBase&max_cells=100" {
    param($p) $p.context.snapshot_id -and $p.forecast -and $p.map -and $null -ne $p.actions -and $p.advisory
}

$PanelPayloads = @($Current, $Forecast, $Stations, $Map, $Intelligence, $Actions, $Advisory) | Where-Object { $null -ne $_ }
$SnapshotIds = @($PanelPayloads | ForEach-Object { $_.context.snapshot_id } | Select-Object -Unique)
$ContextKeys = @($PanelPayloads | ForEach-Object { "$($_.context.city.city_id)|$($_.context.pollutant)|$($_.context.horizon)|$($_.context.issue_timestamp)" } | Select-Object -Unique)
Add-Check "cross-panel-context-integrity" "internal://panel-context" 200 0 ($SnapshotIds.Count -eq 1 -and $ContextKeys.Count -eq 1) $(if ($SnapshotIds.Count -eq 1 -and $ContextKeys.Count -eq 1) { "" } else { "Panel contexts did not match" })
$CategoryConsistent = $null -ne $Current -and $null -ne $Forecast -and $null -ne $Advisory -and $null -ne $Snapshot -and $Current.data.category -eq $Snapshot.current.category -and $Forecast.data.peak.category -eq $Snapshot.forecast.peak.category -and $Forecast.data.peak.category -eq $Advisory.data.category -and $Forecast.data.peak.colour -eq $Advisory.data.colour -and $Forecast.data.peak.aqi -eq $Advisory.data.aqi
$ActionPriorities = @("High", "Medium", "Routine")
$InvalidActions = @($Actions.data | Where-Object { $_.priority -notin $ActionPriorities -or $_.evidence_score -lt 25 -or -not $_.source_id })
$InvalidSnapshotActions = @($Snapshot.actions | Where-Object { $_.priority -notin $ActionPriorities -or $_.evidence_score -lt 25 -or -not $_.source_id })
$ActionSourceIds = @($Actions.data | ForEach-Object { $_.source_id } | Select-Object -Unique)
$PriorityConsistent = $null -ne $Intelligence -and $null -ne $Actions -and $null -ne $Forecast -and $null -ne $Snapshot -and $Intelligence.data.priority -eq $Forecast.data.priority -and $Intelligence.data.priority -eq $Snapshot.intelligence.priority -and $Forecast.data.priority -eq $Snapshot.forecast.priority -and $InvalidActions.Count -eq 0 -and $InvalidSnapshotActions.Count -eq 0 -and $ActionSourceIds.Count -eq @($Actions.data).Count
Add-Check "decision-label-consistency" "internal://decision-labels" 200 0 ($CategoryConsistent -and $PriorityConsistent) $(if ($CategoryConsistent -and $PriorityConsistent) { "" } else { "Advisory category or action priority did not match its canonical forecast context" })

Test-HtmlEndpoint "frontend-root" "http://127.0.0.1:$FrontendPort/"
Test-HtmlEndpoint "frontend-dashboard-route" "http://127.0.0.1:$FrontendPort/dashboard"

$Passed = @($Checks | Where-Object { $_.passed }).Count
$Failed = @($Checks | Where-Object { -not $_.passed }).Count
$Report = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    backend_port = $BackendPort
    frontend_port = $FrontendPort
    passed = $Passed
    failed = $Failed
    checks = $Checks
}
$ReportPath = Join-Path $Root "outputs\reports\demo_verification_report.json"
New-Item -ItemType Directory -Force (Split-Path $ReportPath -Parent) | Out-Null
$Report | ConvertTo-Json -Depth 7 | Set-Content $ReportPath -Encoding UTF8

Write-Host "AirView verification: $Passed passed, $Failed failed."
$Checks | ForEach-Object {
    $Mark = if ($_.passed) { "PASS" } else { "FAIL" }
    Write-Host ("{0,-5} {1,-32} HTTP {2} ({3} ms)" -f $Mark, $_.name, $_.status, $_.duration_ms)
}
if ($Failed -gt 0) { exit 1 }
