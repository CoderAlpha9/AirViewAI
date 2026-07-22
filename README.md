# AirView AI

AirView AI is an operational air-quality decision-support dashboard for Indian cities. It combines live numerical air-quality and weather forecasts, nearby monitoring stations when available, a persisted city-agnostic residual model, thermal anomalies and mapped source context into consistent current conditions, forecasts, one-kilometre planning grids, interventions and citizen guidance.

The five quick-select cities are Delhi NCR, Agra, Amritsar, Lucknow and Ludhiana. Nominatim-backed search can resolve additional Indian cities without changing the dashboard workflow.

## Architecture

- **React, TypeScript and Vite:** progressively loads each dashboard panel and rejects stale or context-mismatched responses.
- **FastAPI:** resolves cities, calls providers concurrently, assembles canonical snapshots and serves independent live panels.
- **ML service:** loads persisted pollutant/horizon artifacts and transfers only validation-selected persistence-trained corrections onto live CAMS trajectories and grid cells.
- **Leaflet:** fits the resolved city boundary, grid and stations; it renders GeoJSON cells as a single layer for responsive interaction.

Every panel context includes city, pollutant, horizon, issue time, snapshot ID, freshness and coverage type. Successful panels remain visible if an unrelated provider fails.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Live data providers

| Provider | Operational use | Credential |
|---|---|---|
| CPCB via Data.gov.in | Indian station observations | Optional `DATA_GOV_IN_API_KEY` |
| OpenAQ v3 | Nearby stations and recent observations | Optional `OPENAQ_API_KEY` |
| CAMS via Open-Meteo Air Quality | Current and hourly PM2.5/PM10 numerical fields | None |
| Open-Meteo Weather | Current/hourly meteorology | None |
| NASA FIRMS | Near-real-time thermal anomalies | Optional `NASA_FIRMS_MAP_KEY` |
| OSM Overpass | Road, industry and construction context | None |
| OSM Nominatim | Indian city search, centres and boundaries | None |

Missing credentials or provider outages produce explicit unavailable/partial metadata. They never trigger archived-reading substitution. CAMS may provide a clearly labelled modelled current value when no usable station observation exists.

See [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Forecast and coverage

The forecast starts from live CAMS/Open-Meteo hourly values. Six persisted HistGradientBoosting artifacts cover PM2.5 and PM10 at 24, 48 and 72 hours. They were trained to predict future station observation minus the issue-time station observation—a persistence residual. Archived CAMS fields were not present in training. Leave-one-city-out validation selects whether transferring that learned correction or applying zero learned correction is safer for each pollutant/horizon; this is not a validated CAMS-error model. Spatial live-station residuals use up to five freshness-, distance- and provider-ranked stations and decay with forecast lead time.

- **Station-corrected:** one or more usable nearby monitoring stations contributed a spatial residual.
- **Model-based:** no usable station correction was available; confidence is reduced and the UI labels this explicitly.

The grid is a one-kilometre operational planning layer, not a regulatory dispersion model. See [docs/ML_METHODOLOGY.md](docs/ML_METHODOLOGY.md).

Unqualified AQI categories and category colours describe the current concentration only. Forecast peaks are labelled as forecasts. Map cells use the backend current-category palette with transparent fills and retain the selected-horizon forecast as a separate tooltip value.

## Setup

Prerequisites: Windows PowerShell, Python 3.10+ and Node.js/npm.

```powershell
.\scripts\bootstrap.ps1
Copy-Item .env.example backend\.env
```

Provider credentials are optional. Leave unused values blank. `backend/.env` is ignored by Git.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AIRVIEW_API_HOST` | `127.0.0.1` | API bind host |
| `AIRVIEW_API_PORT` | `8000` | API port metadata |
| `AIRVIEW_CORS_ORIGINS` | localhost/127.0.0.1 on 5173 | Allowed frontend origins |
| `AIRVIEW_LOG_LEVEL` | `INFO` | Backend logging level |
| `AIRVIEW_LIVE_PROVIDER_TIMEOUT_SECONDS` | `20` | Provider timeout budget |
| `AIRVIEW_OPERATIONAL_CACHE_SECONDS` | `600` | Operational cache duration |
| `DATA_GOV_IN_API_KEY` | blank | Optional CPCB/Data.gov.in access |
| `OPENAQ_API_KEY` | blank | Optional OpenAQ v3 access |
| `NASA_FIRMS_MAP_KEY` | blank | Optional FIRMS access |
| `COPERNICUS_CLIENT_ID/SECRET` | blank | Offline ingestion utilities; not required by the dashboard |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | Frontend API origin |

## Run from the repository root

Backend and frontend in separate terminals:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_frontend.ps1
```

Combined launcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

Custom ports remain synchronized across backend CORS, frontend API configuration and verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1 -BackendPort 8100 -FrontendPort 5180
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_demo.ps1 -BackendPort 8100 -FrontendPort 5180
```

Verify and stop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_demo.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_demo.ps1
```

Dashboard: `http://127.0.0.1:5173/`
API docs: `http://127.0.0.1:8000/docs`

## Validation

```powershell
.\.venv\Scripts\python.exe -m ruff check backend ml
.\.venv\Scripts\python.exe -m ruff format --check backend ml
.\.venv\Scripts\python.exe -m pytest backend\tests ml\tests
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_demo.ps1
```

## Known external limitations

- Station availability depends on provider coverage, credentials, freshness and rate limits; many cities have model-based coverage.
- Data.gov.in, OpenAQ, FIRMS, Overpass and Nominatim can throttle or fail independently.
- Open-Meteo/CAMS is a numerical model, not a ground observation.
- FIRMS detects thermal anomalies but does not identify emission source type.
- OSM features are contextual proxies and are not source apportionment.
- The residual validation used archived station persistence as its causal baseline because archived cell-level CAMS inputs were not retained. Reported validation is not a direct historical evaluation of the live CAMS-plus-residual stack.
- Citizen guidance is public-information support, not medical advice; interventions require field verification.

## Repository layout

`backend/` contains the operational API, `frontend/` the production dashboard, `ml/` training/evaluation utilities, `models/` persisted artifacts, `docs/` methodology and delivery documentation, and `scripts/` root-level setup/run/verification commands.

## License

[MIT](LICENSE)
