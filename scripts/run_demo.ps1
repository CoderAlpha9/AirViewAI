param([int]$BackendPort=8000,[int]$FrontendPort=5173,[switch]$NoBrowser,[switch]$SkipBuild,[switch]$ForceRestartDemoProcesses)
$ErrorActionPreference='Stop'; $root=Split-Path $PSScriptRoot -Parent; $state=Join-Path $root '.demo-processes.json'; $python=Join-Path $root '.venv\Scripts\python.exe'
if(!(Test-Path $python)){throw 'Missing .venv. Run scripts/bootstrap.ps1 first.'}; if(!(Test-Path (Join-Path $root 'frontend\node_modules'))){throw 'Missing frontend/node_modules. Run npm --prefix frontend install.'}
foreach($path in @('data\processed\india\station_hourly_features.parquet','outputs\reports\enforcement_priority_report.json','outputs\examples\demo_presets.json')){if(!(Test-Path (Join-Path $root $path))){throw "Missing required artifact: $path"}}
if(Test-Path $state){if(!$ForceRestartDemoProcesses){throw 'A demo state file exists. Run scripts/stop_demo.ps1 or use -ForceRestartDemoProcesses.'}; & (Join-Path $PSScriptRoot 'stop_demo.ps1')}
foreach($port in @($BackendPort,$FrontendPort)){if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue){throw "Port $port is already occupied."}}
if(!$SkipBuild){npm --prefix (Join-Path $root 'frontend') run build | Out-Host}
$backend=Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',$BackendPort -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru
$frontendCommand="npm.cmd --prefix `"$(Join-Path $root 'frontend')`" run dev -- --host 127.0.0.1 --port $FrontendPort";$frontend=Start-Process -FilePath 'cmd.exe' -ArgumentList '/c',$frontendCommand -WindowStyle Hidden -PassThru
for($i=0;$i -lt 30;$i++){try{if((Invoke-WebRequest "http://127.0.0.1:$BackendPort/api/health" -UseBasicParsing).StatusCode -eq 200 -and (Invoke-WebRequest "http://127.0.0.1:$FrontendPort/" -UseBasicParsing).StatusCode -eq 200){break}}catch{};Start-Sleep -Milliseconds 500}; if($i -eq 30){throw 'Demo services did not become ready.'}
@{backend_pid=$backend.Id;frontend_pid=$frontend.Id;backend_port=$BackendPort;frontend_port=$FrontendPort;started_at=(Get-Date).ToUniversalTime().ToString('o')}|ConvertTo-Json|Set-Content $state -Encoding UTF8
Write-Host "Frontend: http://127.0.0.1:$FrontendPort  Backend: http://127.0.0.1:$BackendPort  Docs: http://127.0.0.1:$BackendPort/docs"
