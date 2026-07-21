# Geospatial units

Interchange geometries use WGS84/EPSG:4326. Distance buffers and grid construction project to
EPSG:7755 before converting back to WGS84. The default hyperlocal unit is an approximately 1 km
grid constrained to an eligible city AOI; a nationwide grid is intentionally not generated.

Geometry preference is GHSL urban geometry, then reliable OSM or official boundary, then a clearly
labelled monitoring-station buffer fallback. Ward boundaries are optional only: unavailable or
unreliable ward boundaries do not prevent city or grid processing.

