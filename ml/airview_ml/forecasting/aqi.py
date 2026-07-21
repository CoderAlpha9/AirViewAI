"""Indian National AQI pollutant sub-index configuration (CPCB NAQI, 2014)."""
from __future__ import annotations

from typing import Literal

# PM breakpoints are 24-hour concentrations in µg/m³. Concentration forecasts stay
# separate; callers must only derive this sub-index when the averaging window is valid.
PM25 = ((0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200), (91, 120, 201, 300), (121, 250, 301, 400), (251, 500, 401, 500))
PM10 = ((0, 50, 0, 50), (51, 100, 51, 100), (101, 250, 101, 200), (251, 350, 201, 300), (351, 430, 301, 400), (431, 600, 401, 500))
Category = Literal["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]

def sub_index(value: float | None, pollutant: str, unit: str = "ug/m3") -> int | None:
    if value is None or unit.lower().replace("³", "3") not in {"ug/m3", "µg/m3"}:
        return None
    table = PM25 if pollutant == "pm2_5" else PM10 if pollutant == "pm10" else ()
    for lo, hi, ilo, ihi in table:
        if lo <= value <= hi:
            return round((ihi - ilo) / (hi - lo) * (value - lo) + ilo)
    return None

def category(index: int | None) -> Category | None:
    if index is None:
        return None
    if index <= 50:
        return "Good"
    if index <= 100:
        return "Satisfactory"
    if index <= 200:
        return "Moderate"
    if index <= 300:
        return "Poor"
    if index <= 400:
        return "Very Poor"
    if index <= 500:
        return "Severe"
    return None
