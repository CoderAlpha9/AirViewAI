# Demo guide

## Start

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

The launcher verifies dependencies and six required model artifacts, starts hidden backend/frontend processes, waits for health, writes only ignored runtime logs, and reports optional providers without configured credentials.

For separate terminals:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_frontend.ps1
```

## Suggested walkthrough

1. Open `http://127.0.0.1:5173/` and note that controls remain responsive while panels arrive independently.
2. Switch among Delhi NCR, Agra, Amritsar, Lucknow and Ludhiana.
3. Search for Mysuru, Jaipur or Kochi and select the result.
4. Change PM2.5/PM10 and 24/48/72-hour windows; confirm the header and snapshot change before new panels render.
5. Inspect the current category, separately labelled forecast peak, monitoring coverage, map cells, source evidence, intervention and citizen guidance.
6. On the map, confirm the resolved city fit, transparent backend category colours and legend, current/forecast tooltip values, issue time, station markers and FIRMS markers when their providers are available.
7. Read the fixed next-24-hour PM2.5 comparison; its peak value, AQI, category, colour and forecast priority share one snapshot.

## Automated verification

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_demo.ps1
```

The script checks health, operational status, all five defaults, Indian city search, a searched-city current/forecast/stations/grid/source/actions/advisory/snapshot workflow, cross-panel context integrity, grid variation and both frontend routes. It writes an ignored JSON report to `outputs/reports/demo_verification_report.json`.

## Stop

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_demo.ps1
```

Only processes recorded in `.demo-processes.json` are stopped.

## Expected limitations

Zero nearby stations or unavailable FIRMS/OSM evidence is a valid degraded state. It must be labelled locally and must not prevent CAMS-backed panels from rendering. Search and tile loading require network access. If CAMS/Open-Meteo itself is unavailable, the forecast-dependent panels remain unavailable rather than showing archived values.
