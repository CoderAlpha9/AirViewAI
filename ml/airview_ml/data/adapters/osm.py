from datetime import datetime, timezone
from typing import Any

from airview_ml.data.contracts import SourceResult
from airview_ml.data.http import CachedHttpClient


class OsmAdapter:
    source = "openstreetmap_overpass"
    official_url = "https://www.openstreetmap.org/copyright"

    def __init__(self, client: CachedHttpClient) -> None:
        self.client = client

    @staticmethod
    def city_query(south: float, west: float, north: float, east: float) -> str:
        bbox = f"{south},{west},{north},{east}"
        return f"[out:json][timeout:60];(way[highway]({bbox});node[amenity~\"hospital|clinic|school\"]({bbox});way[landuse~\"industrial|construction\"]({bbox});node[railway]({bbox}););out tags center;"

    def fetch_city(self, south: float, west: float, north: float, east: float) -> tuple[list[dict[str, Any]], SourceResult]:
        try:
            payload, cache_path, _ = self.client.post_json(
                self.source,
                "https://overpass-api.de/api/interpreter",
                data={"data": self.city_query(south, west, north, east)},
                headers={"User-Agent": "AirViewAI/0.1 local-development"},
            )
            elements = payload.get("elements", [])
        except Exception as exc:
            return [], SourceResult(source=self.source, status="failed", retrieved_at_utc=datetime.now(timezone.utc), official_url=self.official_url, licence="ODbL", error=str(exc), value_kind="proxy")
        return elements, SourceResult(source=self.source, status="success", retrieved_at_utc=datetime.now(timezone.utc), row_count=len(elements), cache_path=str(cache_path), geographic_coverage="configured city AOI", official_url=self.official_url, licence="ODbL", value_kind="proxy", processing_steps=["cached conservative Overpass query", "tag extraction"])

    @staticmethod
    def tag_features(elements: list[dict[str, Any]]) -> dict[str, int]:
        tags = [element.get("tags", {}) for element in elements]
        return {
            "healthcare_location_count": sum(tag.get("amenity") in {"hospital", "clinic", "nursing_home"} for tag in tags),
            "education_location_count": sum(tag.get("amenity") in {"school", "college", "university"} for tag in tags),
            "industrial_feature_count": sum(tag.get("landuse") == "industrial" for tag in tags),
            "construction_feature_count": sum(tag.get("landuse") == "construction" for tag in tags),
            "traffic_emission_pressure_proxy_feature_count": sum("highway" in tag for tag in tags),
        }
