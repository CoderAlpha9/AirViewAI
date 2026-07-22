"""Pure scoring primitives; all values are relative screening indicators, never emissions."""
# ruff: noqa
from __future__ import annotations

from math import asin, atan2, cos, exp, radians, sin, sqrt


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = sin(radians(lat2-lat1)/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(radians(lon2-lon1)/2)**2
    return 12742 * asin(sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    x = sin(radians(lon2-lon1))*cos(radians(lat2)); y = cos(radians(lat1))*sin(radians(lat2))-sin(radians(lat1))*cos(radians(lat2))*cos(radians(lon2-lon1))
    return (atan2(x, y)*180/3.141592653589793+360) % 360


def angular_difference(a: float, b: float) -> float: return abs((a-b+180) % 360-180)
def wind_alignment(source_bearing: float, wind_from: float | None) -> float:
    return 0.0 if wind_from is None else max(0.0, cos(radians(angular_difference(source_bearing, wind_from))))
def distance_decay(distance: float, scale: float = 35.0) -> float: return exp(-max(0.0, distance)/scale)
def temporal_decay(hours: float, half_life: float = 12.0) -> float: return exp(-0.69314718056*max(0.0, hours)/half_life)
def rain_attenuation(rain_mm: float | None) -> float: return 1.0 / (1.0 + max(0.0, rain_mm or 0.0))
def stagnation(wind_speed: float | None, rain_mm: float | None) -> float:
    return max(0.0, min(1.0, (1.0-min(1.0, (wind_speed or 0.0)/4.0))*rain_attenuation(rain_mm)))
def tier(score: float, confidence: float) -> str:
    if confidence < .35: return "Insufficient evidence"
    if score >= .75: return "Critical"
    if score >= .55: return "High"
    if score >= .35: return "Medium"
    return "Watch"
