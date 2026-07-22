# AirView AI

**ET AI Hackathon 2026 - Problem Statement 5: AI-Powered Urban Air Quality Intelligence for Smart City Intervention**

AirView AI is a five-city operational air-quality decision-support prototype for Agra, Amritsar, Delhi NCR, Lucknow, and Ludhiana. It combines current station observations where available, numerical air-quality and weather forecasts, NASA FIRMS thermal-anomaly evidence, OpenStreetMap source proxies, and validated historical models to turn monitoring data into 24-72 hour forecasts, source-influence screening, geospatial intervention views, prioritised actions, and multilingual citizen guidance.

The product is designed for a hackathon demonstration, but its outputs remain source-honest:

- current feeds are used when providers respond;
- station observations are distinguished from modelled CAMS current values;
- the dashboard falls back to a clearly labelled validated replay when current providers fail;
- source results are evidence-supported screening, not regulatory source apportionment;
- intervention values are scenario sensitivities, not causal impact estimates;
- the 1 km view is a transparent intervention-planning downscaling around the selected station, not an independently resolved atmospheric simulation.

## Final demo experience

The production-facing frontend contains one focused command dashboard. It exposes no development logs, validation pages, raw stack traces, or internal audit views.

The dashboard provides:

- **Operational / validated replay modes** with explicit provenance and freshness
- **PM2.5 and PM10 forecasts** for 24, 48, or 72 hours
- **Current concentration** from recent OpenAQ station data where available, otherwise a labelled CAMS modelled current value
- **Forecast fusion** using CAMS, live station bias, and validated Ridge endpoint models
- **Actual versus forecast trajectories** in replay mode, persistence/provider baselines, and 90% intervals
- **Exploratory Indian PM AQI-style categories** calculated from rolling 24-hour concentration where enough hours exist
- **Geospatial intervention map** with station, 1 km cells, current/historical FIRMS evidence, wind context, and OpenStreetMap attribution
- **Source-influence screening** across transport, industry, construction/road dust, burning activity, regional thermal anomalies, meteorological accumulation, and unresolved background
- **Priority action queue** with agency, response time, cost tier, assumptions, and sensitivity range
- **Citizen advisories** in English, Hindi, and Punjabi
- **Five-city comparison** with a shared PM2.5 24-hour outlook

## Data and model foundation

The included validated pilot contains approximately:

- 866,000 real OpenAQ sensor observations
- 40,800 station-hour records
- PM2.5 and PM10 coverage for five historical pilot stations
- historical range from February 2025 to March 2026
- 1,111,362 canonical NASA FIRMS thermal-anomaly events
- 1,700 causal station/timestamp FIRMS feature rows
- 23,716 source-influence screening records
- PM2.5 and PM10 models for 24, 48, and 72-hour horizons
- persistence, daily, weekly, and rolling baseline evaluation
- global and city-local Ridge candidates, with persistence retained wherever it performed better

## Live operational path

When the dashboard is in **Operational** mode, the backend attempts the following concurrently:

1. **OpenAQ v3** for recent station observations and hourly history
2. **Open-Meteo Air Quality** for current and future CAMS PM2.5/PM10 fields
3. **Open-Meteo Weather** for wind, precipitation, visibility, pressure, and boundary-layer context
4. **NASA FIRMS near-real-time** for thermal anomalies around the selected city
5. **OpenStreetMap-derived evidence** from the validated local cache

The forecast engine then:

1. prefers a recent station observation when available;
2. uses CAMS current air quality when station data is delayed or unavailable;
3. fuses the future CAMS trajectory with a decaying station/model bias;
4. applies endpoint corrections from validated 24/48/72-hour Ridge models when feature completeness permits;
5. attaches calibrated uncertainty intervals and AQI-style categories;
6. builds a bounded 1 km intervention grid from the city-scale forecast, wind direction, and stagnation context.

All live provider calls use bounded timeouts, retries, and TTL caching. Provider failures never generate fake current readings; the system switches to a labelled replay instead.

## Five-city station contexts

| City | Operational station context | Replay behaviour |
|---|---|---|
| Delhi NCR | Anand Vihar | Same validated station context |
| Agra | Sanjay Palace | Same validated station context |
| Amritsar | Golden Temple | Same validated station context |
| Lucknow | Talkatora | Same validated station context |
| Ludhiana | Punjab Agricultural University | The immutable v1 replay used Civil Line, Jalandhar as a regional Punjab station. This is disclosed in the UI and its spatial evidence is never mixed into the live Ludhiana context. |

## Quick start on Windows

### 1. Install dependencies once

```powershell
.\scripts\bootstrap.ps1
```

### 2. Configure provider credentials

Copy the template only when `backend/.env` is absent:

```powershell
Copy-Item backend\.env.example backend\.env
```

Set the following without committing the file:

```text
OPENAQ_API_KEY=
NASA_FIRMS_MAP_KEY=
DATA_GOV_IN_API_KEY=
COPERNICUS_CLIENT_ID=
COPERNICUS_CLIENT_SECRET=
```

Only OpenAQ and NASA FIRMS are required for their corresponding current evidence. Open-Meteo air-quality and weather forecasts do not require keys. Sentinel-5P is not used in the operational dashboard because the validated prototype recovered no usable pixels.

### 3. Start the complete demo

```powershell
.\scripts\run_demo.ps1
```

Open:

- Dashboard: `http://127.0.0.1:5173/`
- Dashboard alias: `http://127.0.0.1:5173/dashboard`
- API documentation: `http://127.0.0.1:8000/docs`

### 4. Verify the demo

```powershell
.\scripts\verify_demo.ps1
```

### 5. Stop only demo-owned processes

```powershell
.\scripts\stop_demo.ps1
```

The scripts use a demo-specific process state file and do not stop unrelated Python or Node processes.

## Main API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Backend health |
| GET | `/api/operations/status` | Provider and capability status |
| GET | `/api/operations/cities` | Operational city/station registry |
| GET | `/api/operations/dashboard` | Complete live or replay dashboard package |
| GET | `/api/operations/network` | Compact five-city comparison |

Example:

```text
GET /api/operations/dashboard?city_id=delhi-ncr&pollutant=pm2_5&horizon=72&language=en&mode=live
```

Supported values:

- `city_id`: `delhi-ncr`, `agra`, `amritsar`, `lucknow`, `ludhiana`
- `pollutant`: `pm2_5`, `pm10`
- `horizon`: `24`, `48`, `72`
- `language`: `en`, `hi`, `pa`
- `mode`: `live`, `demo`

## Architecture

![AirView AI architecture](docs/architecture/assets/airview-final-architecture.svg)

The detailed flow and trust boundaries are documented in [docs/architecture/system-overview.md](docs/architecture/system-overview.md).

## Validate from source

```powershell
.\.venv\Scripts\python.exe -m ruff check backend ml
.\.venv\Scripts\python.exe -m pytest backend\tests ml\tests
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Repository structure

```text
AirViewAI/
├── backend/                  FastAPI operational service and tests
├── frontend/                 Demo-only React command dashboard
├── ml/                       Reproducible data, forecast, and intelligence pipelines
├── data/                     Cached raw and validated processed evidence
├── models/                   Versioned forecast model artifacts
├── outputs/                  Reports, replay examples, figures, and submission assets
├── docs/                     Architecture, methodology, product, and submission notes
├── scripts/                  Bootstrap, run, verify, and stop workflows
└── README.md
```

## Limitations

- The detailed validated scope is five cities, not full pan-India operational coverage.
- OpenAQ observations may be delayed or absent; CAMS is then labelled as a modelled current value.
- CPCB/Data.gov.in access was unreliable during development and is not required by the demo runtime.
- Sentinel-5P is explicitly unavailable in this prototype after authenticated requests returned zero valid pixels.
- GHSL population exposure is not shown because an official raster was not ingested.
- OSM evidence is unavailable for Agra and Amritsar; live Ludhiana does not reuse the old Jalandhar OSM row.
- Station density is insufficient for a calibrated citywide 1 km atmospheric forecast. The displayed 1 km cells are intervention-planning downscaling and are labelled accordingly.
- Source rankings are likelihood/context indicators rather than confirmed source shares.
- Recommended actions require field verification before enforcement.
- Citizen messages are prototype public information and not medical advice.

## Submission assets

Final submission materials are stored under `docs/submission/` and `outputs/submission/`, including the architecture diagram, presentation deck, demo script, and final validation summary.

## License

[MIT](LICENSE)
