from datetime import datetime, timezone
from typing import Any

from airview_ml.data.contracts import AirQualityRecord, SourceResult
from airview_ml.data.http import CachedHttpClient
from airview_ml.data.normalization import normalise_pollutant
from airview_ml.data.units import convert_pollutant


class CpcbAdapter:
    source = "cpcb_data_gov_in"
    resource_id = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
    official_url = "https://www.data.gov.in/resource/real-time-air-quality-index-various-locations"

    def __init__(self, client: CachedHttpClient, api_key: str | None, request_limit: int = 1_000) -> None:
        self.client = client
        self.api_key = api_key
        self.request_limit = request_limit

    def fetch_latest(self, state: str | None = None, city: str | None = None) -> tuple[list[AirQualityRecord], SourceResult]:
        if not self.api_key:
            return [], SourceResult(
                source=self.source,
                status="credentials_required",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="DATA_GOV_IN_API_KEY",
                licence="NDSAP",
                error="Set DATA_GOV_IN_API_KEY. The official API key is not bundled with this repository.",
            )
        records: list[AirQualityRecord] = []
        offset = 0
        cache_path = None
        try:
            while True:
                params: dict[str, Any] = {
                    "api-key": self.api_key,
                    "format": "json",
                    "offset": offset,
                    "limit": self.request_limit,
                }
                if state:
                    params["filters[state]"] = state
                if city:
                    params["filters[city]"] = city
                payload, cache_path, _ = self.client.get_json(
                    self.source,
                    f"https://api.data.gov.in/resource/{self.resource_id}",
                    params=params,
                )
                page = payload.get("records", []) if isinstance(payload, dict) else []
                records.extend(self.parse_records(page))
                if len(page) < self.request_limit:
                    break
                offset += len(page)
        except Exception as exc:  # surfaced as a source report, not fabricated data
            return [], SourceResult(
                source=self.source,
                status="failed",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="DATA_GOV_IN_API_KEY",
                licence="NDSAP",
                error=str(exc),
            )
        return records, SourceResult(
            source=self.source,
            status="success",
            retrieved_at_utc=datetime.now(timezone.utc),
            row_count=len(records),
            cache_path=str(cache_path) if cache_path else None,
            geographic_coverage="India-wide official current snapshot; subject to provider availability",
            variables=sorted({record.pollutant for record in records}),
            official_url=self.official_url,
            credential_requirement="DATA_GOV_IN_API_KEY",
            licence="NDSAP",
            processing_steps=["paginated API retrieval", "schema-tolerant parsing", "unit normalisation"],
        )

    @staticmethod
    def parse_records(rows: list[dict[str, Any]]) -> list[AirQualityRecord]:
        parsed: list[AirQualityRecord] = []
        retrieved_at = datetime.now(timezone.utc)
        for row in rows:
            pollutant = normalise_pollutant(str(row.get("pollutant_id") or row.get("pollutant") or ""))
            if not pollutant:
                continue
            value = row.get("pollutant_avg")
            try:
                numeric_value = float(value) if value not in (None, "", "NA") else None
            except (TypeError, ValueError):
                numeric_value = None
            unit = row.get("pollutant_unit") or row.get("unit")
            conversion = convert_pollutant(numeric_value, unit, pollutant)
            flags = list(conversion.flags)
            latitude, longitude = _coordinates(row, flags)
            timestamp = _parse_datetime(row.get("last_update"), flags)
            parsed.append(
                AirQualityRecord(
                    source="cpcb_data_gov_in",
                    provider="CPCB via data.gov.in",
                    country_code=str(row.get("country") or "IN"),
                    state=_string_or_none(row.get("state")),
                    city_id=None,
                    city_name=_string_or_none(row.get("city")),
                    station_id=_string_or_none(row.get("station")),
                    station_name=_string_or_none(row.get("station")),
                    sensor_id=None,
                    latitude=latitude,
                    longitude=longitude,
                    pollutant=pollutant,
                    value_original=numeric_value,
                    unit_original=_string_or_none(unit),
                    value_canonical=conversion.value_canonical,
                    unit_canonical=conversion.unit_canonical,
                    observed_at_utc=timestamp,
                    observed_at_local=_string_or_none(row.get("last_update")),
                    source_timezone="Asia/Kolkata",
                    retrieval_time_utc=retrieved_at,
                    is_valid=not any(flag.startswith("invalid") for flag in flags),
                    quality_flags=flags,
                    licence="NDSAP",
                )
            )
        return parsed


def _string_or_none(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None


def _coordinates(row: dict[str, Any], flags: list[str]) -> tuple[float | None, float | None]:
    try:
        latitude = float(row.get("latitude"))
        longitude = float(row.get("longitude"))
        if not (6 <= latitude <= 38 and 68 <= longitude <= 98):
            flags.append("invalid_or_outside_india_coordinates")
        return latitude, longitude
    except (TypeError, ValueError):
        flags.append("invalid_coordinates")
        return None, None


def _parse_datetime(value: Any, flags: list[str]) -> datetime | None:
    if not value:
        flags.append("missing_timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        flags.append("unparseable_timestamp")
        return None
