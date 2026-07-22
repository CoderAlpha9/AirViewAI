from math import asin, cos, radians, sin, sqrt
from typing import Any

from airview_ml.data.normalization import match_city, normalise_city_name, normalise_text


def map_locations(
    locations: list[dict[str, Any]], cities: list[dict[str, Any]], radius_km: float = 55
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for location in locations:
        coordinates = location.get("coordinates") or {}
        latitude, longitude = coordinates.get("latitude"), coordinates.get("longitude")
        name = str(location.get("name") or "")
        locality = location.get("locality")
        candidate = match_city(locality or name, None, cities)
        city = next((item for item in cities if item["slug"] == candidate.matched_slug), None)
        method, confidence, evidence = candidate.reason, candidate.confidence, locality or name
        if city is None:
            station_text = normalise_text(name)
            named_matches = [
                item
                for item in cities
                if normalise_city_name(str(item["name"])) in station_text
                and len(normalise_city_name(str(item["name"]))) >= 4
            ]
            if len(named_matches) == 1:
                city = named_matches[0]
                method, confidence, evidence = (
                    "station_name_contains_configured_city",
                    "medium",
                    name,
                )
        if city is None and latitude is not None and longitude is not None:
            nearest = sorted(
                (
                    (
                        distance_km(
                            latitude, longitude, city_item["latitude"], city_item["longitude"]
                        ),
                        city_item,
                    )
                    for city_item in cities
                ),
                key=lambda item: item[0],
            )
            if nearest and nearest[0][0] <= radius_km:
                city = nearest[0][1]
                method, confidence, evidence = (
                    "coordinate_proximity_to_configured_city",
                    "medium",
                    f"{nearest[0][0]:.1f} km",
                )
        mapped.append(
            {
                "location_id": location["id"],
                "station_id": f"openaq-{location['id']}",
                "station_name": name,
                "latitude": latitude,
                "longitude": longitude,
                "state": city["state"] if city else None,
                "city_id": city["slug"] if city else None,
                "mapping_method": method,
                "mapping_confidence": confidence,
                "mapping_evidence": evidence,
                "unresolved_reason": None
                if city
                else "no locality, station-name evidence, alias, or safe configured-city coordinate match",
            }
        )
    return mapped


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    a = (
        sin(radians(lat_b - lat_a) / 2) ** 2
        + cos(radians(lat_a)) * cos(radians(lat_b)) * sin(radians(lon_b - lon_a) / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(a))
