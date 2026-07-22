# Data sources

| Source | Data used | Key required | Degradation behavior |
|---|---|---|---|
| CPCB/Data.gov.in | Indian station metadata and current PM readings | Optional | Source marked unavailable; OpenAQ or model-based coverage can continue |
| OpenAQ v3 | Nearby locations, sensors, recent measurements | Optional | Source marked unavailable; other station/CAMS paths continue |
| CAMS via Open-Meteo | Current and hourly PM2.5/PM10 numerical fields | No | Current/forecast/map may be unavailable; no archived values are substituted |
| Open-Meteo Weather | Meteorology used by residual features and context | No | Reduced feature completeness and confidence |
| NASA FIRMS | Near-real-time thermal anomalies | Optional | FIRMS count/markers unavailable; other panels continue |
| OSM Overpass | Road, industrial and construction feature counts | No | Source evidence becomes limited; no cached city is silently substituted |
| OSM Nominatim | Indian city search, centre and administrative boundary | No | Search reports a concise temporary-unavailability state; configured defaults remain usable |

Provider timestamps, source names, fallback flags and availability are returned in panel metadata. A station observation is labelled `observed`; CAMS current conditions are labelled `modelled_current`. The application never labels model output as a monitoring reading.

Provider terms, coverage, schemas, latency and rate limits remain external dependencies. Requests use a descriptive user agent, bounded timeouts, limited retry of transient errors and short TTL caches. Invalid authentication or other non-rate-limit 4xx responses are not repeatedly retried.

`COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET` are retained for offline ingestion utilities but are not required by the operational dashboard.
