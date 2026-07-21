import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx

from airview_ml.data.contracts import SourceResult


class FirmsAdapter:
    source = "nasa_firms"
    official_url = "https://firms.modaps.eosdis.nasa.gov/api/area/"

    def __init__(self, map_key: str | None) -> None:
        self.map_key = map_key

    def fetch_area(self, bbox: tuple[float, float, float, float], days: int = 1) -> tuple[list[dict[str, Any]], SourceResult]:
        if not self.map_key:
            return [], SourceResult(
                source=self.source,
                status="credentials_required",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="NASA_FIRMS_MAP_KEY",
                error="Request a free NASA FIRMS MAP_KEY; no key is bundled.",
            )
        bbox_text = ",".join(str(value) for value in bbox)
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{self.map_key}/VIIRS_SNPP_NRT/{bbox_text}/{days}"
        try:
            response = httpx.get(url, timeout=30)
            response.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(response.text)))
        except Exception as exc:
            return [], SourceResult(
                source=self.source,
                status="failed",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="NASA_FIRMS_MAP_KEY",
                error=str(exc),
            )
        return rows, SourceResult(
            source=self.source,
            status="success",
            retrieved_at_utc=datetime.now(timezone.utc),
            row_count=len(rows),
            geographic_coverage=f"bbox {bbox_text}",
            variables=["thermal_anomaly", "frp", "confidence"],
            official_url=self.official_url,
            credential_requirement="NASA_FIRMS_MAP_KEY",
            processing_steps=["FIRMS area CSV retrieval", "thermal anomaly parsing"],
        )

    @staticmethod
    def influence_features(events: list[dict[str, Any]], latitude: float, longitude: float) -> dict[str, float]:
        # Distances are approximate great-circle distances; wind alignment is calculated only when wind input exists upstream.
        distances = [_haversine_km(latitude, longitude, float(event["latitude"]), float(event["longitude"])) for event in events]
        return {"thermal_anomaly_count_25km": sum(distance <= 25 for distance in distances), "thermal_anomaly_count_50km": sum(distance <= 50 for distance in distances), "thermal_anomaly_count_100km": sum(distance <= 100 for distance in distances), "thermal_anomaly_count_300km": sum(distance <= 300 for distance in distances), "nearest_thermal_anomaly_distance_km": min(distances) if distances else None}


def _haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    latitude_delta = radians(lat_b - lat_a)
    longitude_delta = radians(lon_b - lon_a)
    value = sin(latitude_delta / 2) ** 2 + cos(radians(lat_a)) * cos(radians(lat_b)) * sin(longitude_delta / 2) ** 2
    return 6371 * 2 * asin(sqrt(value))
