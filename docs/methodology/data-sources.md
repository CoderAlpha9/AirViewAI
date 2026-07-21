# Data sources and provenance

AirView AI preserves source ownership, retrieval time, licence/policy, original values and units,
and processing steps. A configured adapter is not reported as live until a real request succeeds.

| Source | Role | Access | Value classification | Current requirement |
|---|---|---|---|---|
| CPCB via Data.gov.in | Current national AQI/pollutant snapshot | Official API | Observed provider values | `DATA_GOV_IN_API_KEY` |
| OpenAQ v3 | Location, station, sensor, latest and targeted history discovery | Official API | Observed provider values | `OPENAQ_API_KEY` |
| OpenAQ AWS archive | Bulk historical measurement partitions | Public unsigned S3 | Observed provider values | India location IDs from OpenAQ discovery |
| Open-Meteo | Historical reanalysis and operational weather | Keyless API | Modelled/reanalysis, not local station observations | None |
| Copernicus Sentinel-5P | NO2, CO, SO2, aerosol-index and QA aggregates | OAuth API | Provider-derived satellite columns, not ground concentrations | Client ID and secret |
| NASA FIRMS | Satellite-detected thermal anomalies | Official API | Observed satellite detection | `NASA_FIRMS_MAP_KEY` |
| OpenStreetMap/Geofabrik | Static spatial and vulnerability-location proxies | Overpass / regional extracts | Proxy | None |
| GHSL | Modelled population, built-up and urban geometry | Official products | Modelled | Verified direct product URL/subset |

Data.gov.in is an official CPCB source under NDSAP. OpenStreetMap-derived features retain ODbL
attribution. Provider-specific OpenAQ licences remain in source metadata. The pipeline does not
claim a regulatory-grade source apportionment from static proxies or satellite products.

