# City eligibility

The pipeline evaluates four independent eligibility levels. Thresholds live in
`airview_ml.data.config.EligibilityThresholds` and are not scattered through adapters.

| Level | Requirement |
|---|---|
| National display | At least one valid station/current reading and valid coordinates |
| Forecast | National display plus minimum history and hourly completeness |
| Hyperlocal | Forecast eligibility, multiple spatially separated stations, and a valid city geometry |
| Intervention intelligence | Forecast eligibility plus static source proxies and population/vulnerability coverage |

Exclusion reasons include no valid coordinates, insufficient history, excessive missingness,
unsupported units, no recent readings, duplicate station identity, unavailable geometry, and API
unavailability. The score is a data-readiness score, never model accuracy.

