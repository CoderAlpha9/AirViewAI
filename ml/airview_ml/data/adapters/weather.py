from datetime import datetime, timezone
from typing import Any

from airview_ml.data.contracts import SourceResult
from airview_ml.data.http import CachedHttpClient

HOURLY_VARIABLES = (
    "temperature_2m,relative_humidity_2m,precipitation,rain,surface_pressure,cloud_cover,"
    "visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code,"
    "shortwave_radiation,boundary_layer_height"
)


class OpenMeteoAdapter:
    source = "open_meteo"
    official_url = "https://open-meteo.com/en/docs"

    def __init__(self, client: CachedHttpClient) -> None:
        self.client = client

    def fetch_historical(
        self, latitude: float, longitude: float, start_date: str, end_date: str, location_id: str
    ) -> tuple[list[dict[str, Any]], SourceResult]:
        return self._fetch(
            "https://archive-api.open-meteo.com/v1/archive",
            latitude,
            longitude,
            {"start_date": start_date, "end_date": end_date},
            location_id,
            "modelled",
        )

    def fetch_forecast(
        self, latitude: float, longitude: float, location_id: str
    ) -> tuple[list[dict[str, Any]], SourceResult]:
        return self._fetch(
            "https://api.open-meteo.com/v1/forecast",
            latitude,
            longitude,
            {"forecast_days": 3},
            location_id,
            "modelled",
        )

    def _fetch(
        self,
        url: str,
        latitude: float,
        longitude: float,
        date_params: dict[str, Any],
        location_id: str,
        value_kind: str,
    ) -> tuple[list[dict[str, Any]], SourceResult]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": HOURLY_VARIABLES,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            **date_params,
        }
        try:
            payload, cache_path, _ = self.client.get_json(self.source, url, params=params)
            rows = self.parse_hourly(payload, location_id)
        except Exception as exc:
            return [], SourceResult(
                source=self.source,
                status="failed",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                error=str(exc),
                value_kind="modelled",
            )
        return (
            rows,
            SourceResult(
                source=self.source,
                status="success",
                retrieved_at_utc=datetime.now(timezone.utc),
                row_count=len(rows),
                cache_path=str(cache_path),
                date_range={
                    "start": rows[0]["observed_at_utc"] if rows else None,
                    "end": rows[-1]["observed_at_utc"] if rows else None,
                },
                geographic_coverage=f"coordinate-level weather for {location_id}",
                variables=list(payload.get("hourly", {}).keys()),
                official_url=self.official_url,
                licence="Open-Meteo terms and upstream model attribution",
                processing_steps=[
                    "coordinate-level request",
                    "UTC alignment",
                    "provider unit preservation",
                ],
                value_kind=value_kind,  # Open-Meteo data are reanalysis/model output, not station observations.
            ),
        )

    @staticmethod
    def parse_hourly(payload: dict[str, Any], location_id: str) -> list[dict[str, Any]]:
        hourly = payload.get("hourly", {})
        units = payload.get("hourly_units", {})
        times = hourly.get("time", [])
        rows: list[dict[str, Any]] = []
        for index, time_value in enumerate(times):
            rows.append(
                {
                    "location_id": location_id,
                    "observed_at_utc": datetime.fromisoformat(time_value)
                    .replace(tzinfo=timezone.utc)
                    .isoformat(),
                    "source_timezone": payload.get("timezone", "UTC"),
                    "source_model": payload.get("timezone_abbreviation"),
                    "value_kind": "modelled",
                    "units": units,
                    **{
                        key: values[index] if index < len(values) else None
                        for key, values in hourly.items()
                        if key != "time"
                    },
                }
            )
        return rows
