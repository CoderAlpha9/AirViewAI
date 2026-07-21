# AirView AI system overview

## Purpose

AirView AI is planned as a decision-support platform that connects heterogeneous urban and
environmental evidence to traceable city interventions and public-health communication. The
foundation currently implements contracts, configuration, a health API, and a frontend
connectivity check. It does not yet ingest live data or run trained models.

## Planned end-to-end flow

```text
CAAQMS + weather + traffic + satellite + land use
         + construction + industrial + waste-burning data
                              |
                              v
                    Ingestion and validation
                              |
                              v
              Spatial-temporal feature engineering
                              |
                              v
                    24–72 hour AQI forecasting
                              |
                              v
                      Source attribution
                              |
                              v
       Hotspot and vulnerable-population analysis
                              |
                              v
                  Enforcement prioritisation
                              |
                              v
              Intervention impact estimation
                              |
                              v
              Multilingual citizen advisories
                              |
                              v
                  City command dashboard
```

## Component boundaries

### Data plane

Adapters will acquire source data without hiding its provenance. Validation will check schemas,
units, timestamp alignment, coordinates, missingness, and quality flags before preserving raw
inputs and producing normalised interim tables. CSV and JSON are the prototype formats; the
backend storage protocol allows a later SQLite adapter without coupling API routes to files.

### Intelligence plane

The `airview_ml` package separates data preparation, feature engineering, forecasting,
attribution, intervention modelling, and evaluation. Model artifacts use Joblib and carry model,
feature, data-window, and evaluation metadata. XGBoost is optional; scikit-learn remains the
portable fallback. Persistence forecasting is a required baseline.

### Service plane

FastAPI owns configuration, validated API schemas, orchestration services, and future persistence
adapters. Domain contracts cover cities, wards, stations, observations, forecasts, attribution,
recommendations, advisories, and vulnerable locations. API versioning and authorization will be
introduced before external deployment.

### Experience plane

The React application will combine geospatial views, forecast timelines, source evidence,
vulnerability context, enforcement queues, intervention scenarios, and multilingual advisories.
The present landing screen only reports whether the backend health endpoint is reachable.

## Trust and governance

- Every datum must retain source, time, geography, units, and quality metadata.
- Simulated and semi-synthetic data must be labelled at source and in every user-facing output.
- Recommendations must expose evidence and uncertainty; they remain decision support.
- Evaluation must report comparable baselines and must not use fabricated performance values.
- Live CPCB, satellite, or municipal integration may only be claimed after a working adapter is
  connected, monitored, and documented.

