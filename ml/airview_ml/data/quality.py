from collections import Counter
from collections.abc import Iterable

from airview_ml.data.contracts import AirQualityRecord, DataQualityIssue

PHYSICALLY_HIGH = {"pm2_5": 2_000, "pm10": 3_000, "no2": 2_000, "so2": 2_000, "o3": 2_000, "co": 100}


def validate_air_quality(records: Iterable[AirQualityRecord]) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    seen: Counter[tuple[object, ...]] = Counter()
    for record in records:
        identity = (record.station_id, record.pollutant, record.observed_at_utc, record.value_original)
        seen[identity] += 1
        if not record.station_id:
            issues.append(DataQualityIssue("missing_station_id", "warning", "Observation has no station identity", record.source))
        if record.latitude is None or record.longitude is None:
            issues.append(DataQualityIssue("invalid_coordinates", "warning", "Observation has no valid coordinates", record.source))
        if record.value_original is not None and record.value_original < 0:
            issues.append(DataQualityIssue("impossible_negative_value", "error", "Pollutant values cannot be negative", record.source))
        threshold = PHYSICALLY_HIGH.get(record.pollutant)
        if threshold is not None and record.value_canonical is not None and record.value_canonical > threshold:
            issues.append(DataQualityIssue("physically_implausible_high_value", "warning", "Value retained but exceeds conservative screening threshold", record.source))
        if "unsupported_or_incompatible_unit" in record.quality_flags:
            issues.append(DataQualityIssue("unsupported_units", "warning", "Original value retained; canonical conversion intentionally omitted", record.source))
    for identity, count in seen.items():
        if count > 1:
            issues.append(DataQualityIssue("duplicate_observation", "warning", f"Duplicate observation identity appears {count} times", record_id=str(identity)))
    return issues
