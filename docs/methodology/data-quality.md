# Data quality and missing-data behaviour

Raw responses are retained. Validation adds quality flags rather than deleting every extreme value.
Checks cover station identity, India-coordinate bounds, pollutant recognition, original-unit
compatibility, negative values, conservative high-value screening, duplicates, timestamps, and
source failures. Missing values remain missing.

Canonical station rows retain `value_original`, `unit_original`, `value_canonical`, and
`unit_canonical`. CO conversion between µg/m³ and mg/m³ is supported; incompatible physical
quantities, such as Sentinel-5P columns and ground concentrations, are never converted to match.

All internal timestamps are UTC. Source-local timestamp text and timezone metadata are retained.
Open-Meteo values are labelled modelled/reanalysis. Satellite and OSM values are respectively
provider-derived and proxy values.

