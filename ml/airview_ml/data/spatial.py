from collections.abc import Iterable
from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import Point, Polygon, box
from shapely.ops import transform

WGS84 = "EPSG:4326"
INDIA_DISTANCE_CRS = "EPSG:7755"


@dataclass(frozen=True)
class CityGeometry:
    city_id: str
    geometry: Polygon
    source: str
    boundary_type: str
    confidence: str
    fallback_method: str | None = None


def station_buffer_geometry(
    city_id: str, stations: Iterable[tuple[float, float]], buffer_m: int = 5_000
) -> CityGeometry | None:
    points = [Point(longitude, latitude) for latitude, longitude in stations]
    if not points:
        return None
    to_projected = Transformer.from_crs(WGS84, INDIA_DISTANCE_CRS, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(INDIA_DISTANCE_CRS, WGS84, always_xy=True).transform
    projected = [transform(to_projected, point) for point in points]
    geometry = transform(
        to_wgs84,
        projected[0].buffer(buffer_m)
        if len(projected) == 1
        else _union_buffers(projected, buffer_m),
    )
    return CityGeometry(
        city_id,
        geometry,
        "monitoring_station_buffer",
        "fallback_buffer",
        "low",
        f"{buffer_m}m station buffer",
    )


def _union_buffers(points: list[Point], buffer_m: int):
    geometry = points[0].buffer(buffer_m)
    for point in points[1:]:
        geometry = geometry.union(point.buffer(buffer_m))
    return geometry.convex_hull


def generate_grid(
    city_id: str, geometry: Polygon, resolution_m: int = 1_000
) -> list[dict[str, object]]:
    to_projected = Transformer.from_crs(WGS84, INDIA_DISTANCE_CRS, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(INDIA_DISTANCE_CRS, WGS84, always_xy=True).transform
    projected_geometry = transform(to_projected, geometry)
    min_x, min_y, max_x, max_y = projected_geometry.bounds
    cells: list[dict[str, object]] = []
    row = 0
    x = min_x
    while x < max_x:
        y = min_y
        column = 0
        while y < max_y:
            candidate = box(x, y, min(x + resolution_m, max_x), min(y + resolution_m, max_y))
            clipped = candidate.intersection(projected_geometry)
            if not clipped.is_empty:
                wgs84_cell = transform(to_wgs84, clipped)
                cells.append(
                    {
                        "id": f"{city_id}-g{row:04d}-{column:04d}",
                        "city_id": city_id,
                        "geometry_wkt": wgs84_cell.wkt,
                        "crs": WGS84,
                        "resolution_m": resolution_m,
                    }
                )
            y += resolution_m
            column += 1
        x += resolution_m
        row += 1
    return cells
