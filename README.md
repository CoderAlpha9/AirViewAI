# AirView AI

**Team Dextron — ET AI Hackathon 2.0, Problem Statement 5: AI-Powered Urban Air
Quality Intelligence for Smart City Intervention**

AirView AI is a planned smart-city decision-support platform for moving from air-quality
monitoring to intelligent city intervention. It will combine environmental, mobility,
geospatial, meteorological, remote-sensing, and civic data to produce transparent forecasts,
source evidence, enforcement priorities, intervention estimates, and public-health guidance.

The repository currently contains the runnable project foundation: a typed React application, a
FastAPI service, shared domain contracts, an independent ML package boundary, configuration,
tests, data-governance conventions, and architecture documentation. It deliberately does not yet
claim a trained model, live data integration, or operational city recommendations.

## Intended product scope

1. Hyperlocal 24–72 hour AQI forecasting
2. Ward-level or 1 km grid pollution hotspot detection
3. Geospatial pollution source attribution
4. Traffic, construction, industrial, waste-burning, meteorological, satellite, and land-use
   data fusion
5. Enforcement intelligence and prioritised intervention recommendations
6. Intervention impact estimation
7. Citizen health-risk advisories and multilingual communication
8. Vulnerable-population mapping for hospitals, schools, elderly people, children, and outdoor
   workers
9. Multi-city comparative analytics
10. Real-time CAAQMS-style sensor ingestion and remote-sensing adapters
11. Atmospheric dispersion and weather-stagnation features
12. Forecasting, attribution, enforcement, and advisory agents
13. Evaluation against transparent baselines, including persistence forecasting

## Architecture

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router, Axios; dependencies include
  Recharts and Leaflet for later analytical and geospatial views.
- **Backend:** FastAPI, Pydantic, Pandas, NumPy, scikit-learn, and Uvicorn with environment-based
  settings, CORS, typed routes, and a storage service boundary.
- **ML:** an installable `airview_ml` package with separated data, feature, forecasting,
  attribution, intervention, evaluation, and common modules. Joblib is the artifact format.
  XGBoost is supported as an optional dependency; scikit-learn is the default portable fallback.
- **Storage:** CSV/JSON datasets during prototyping, behind an abstraction designed for a later
  SQLite implementation. No heavy production database is included.

See [the system overview](docs/architecture/system-overview.md) for the planned end-to-end flow
and trust boundaries.

## Repository structure

```text
AirViewAI/
├── frontend/            React/Vite application, API client, UI and TypeScript contracts
├── backend/             FastAPI application, schemas, services and API tests
├── ml/                  Installable ML package, artifact area, scripts and tests
├── data/                Raw, interim, processed, reference and labelled demo areas
├── docs/                Architecture, methodology, evaluation and submission notes
├── outputs/             Generated figures, metrics and reports
├── scripts/             Repository setup helpers
├── Makefile             Root development and validation commands
└── README.md
```

## Prerequisites

- Node.js 20 or newer and npm
- Python 3.10 or newer (Python 3.13 is supported)
- PowerShell for the provided one-command Windows bootstrap, or Make for root commands

## Install

From the repository root on Windows, install everything into a local `.venv`:

```powershell
.\scripts\bootstrap.ps1
```

Or install each workspace directly:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e ml
npm --prefix frontend install
```

Copy the environment examples only when local overrides are needed:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Never commit real credentials or secrets.

## Run

Start the API in one terminal:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the web application in another terminal from the repository root:

```powershell
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. The landing page reports the real result of
`GET http://127.0.0.1:8000/api/health`. Interactive API documentation is available at
`http://127.0.0.1:8000/docs`.

Equivalent Make targets are `frontend-install`, `backend-install`, `frontend-dev`,
`backend-dev`, `frontend-build`, `frontend-typecheck`, `frontend-lint`, `backend-test`,
`backend-lint`, `ml-test`, and `validate`.

## Validate

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m ruff check backend ml
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
Set-Location ..
.\.venv\Scripts\python.exe -m pytest ml\tests
```

## Current status

Version `0.1.0` is the project foundation. Implemented today:

- `GET /api/health` and `GET /api/project-info`
- environment settings and local-development CORS
- shared Pydantic schemas and TypeScript domain types
- CSV storage adapter plus an explicit future SQLite boundary
- a responsive landing screen with a real backend connectivity check
- ML package boundaries, optional-XGBoost estimator selection, and Joblib artifact helpers
- backend endpoint tests and frontend lint/type/build tooling

Planned next modules are source adapters and validation, spatial-temporal feature engineering,
forecasting and baseline evaluation, hotspot analysis, attribution, vulnerability analysis,
enforcement prioritisation, impact estimation, advisories, and the command dashboard.

## Data transparency

There is no live CPCB, CAAQMS, satellite, traffic, or municipal integration in this foundation.
The interface contains no fake live readings, wards, model metrics, or claimed accuracy. Any
future simulated or semi-synthetic data will always be labelled honestly in its source metadata,
documentation, and user-facing presentation. A source will only be described as live after a
working adapter is connected, monitored, and documented.

## License

[MIT](LICENSE)
