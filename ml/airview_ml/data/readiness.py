from airview_ml.data.config import EligibilityThresholds
from airview_ml.data.contracts import CityReadinessScore


def readiness_score(city_id: str, metrics: dict[str, float], thresholds: EligibilityThresholds) -> CityReadinessScore:
    station_count = metrics.get("active_station_count", 0)
    history_days = metrics.get("history_days", 0)
    completeness = metrics.get("hourly_completeness", 0)
    coordinate_validity = metrics.get("coordinate_validity", 0)
    recency_hours = metrics.get("recency_hours", float("inf"))
    components = {
        "stations": min(station_count / 5, 1),
        "history": min(history_days / thresholds.minimum_history_days, 1),
        "hourly_completeness": min(completeness / thresholds.minimum_hourly_completeness, 1),
        "pollutant_diversity": min(metrics.get("pollutant_diversity", 0) / 4, 1),
        "coordinate_validity": coordinate_validity,
        "weather": metrics.get("weather_availability", 0),
        "satellite": metrics.get("satellite_availability", 0),
        "firms": metrics.get("firms_availability", 0),
        "spatial": metrics.get("spatial_feature_availability", 0),
        "population": metrics.get("population_availability", 0),
        "recency": 1 if recency_hours <= thresholds.recency_hours else 0,
    }
    score = round(sum(components.values()) / len(components) * 100, 1)
    reasons: list[str] = []
    if station_count < 1:
        reasons.append("no valid station or current reading")
    if history_days < thresholds.minimum_history_days:
        reasons.append("insufficient history")
    if completeness < thresholds.minimum_hourly_completeness:
        reasons.append("excessive missingness")
    if coordinate_validity < 1:
        reasons.append("no valid coordinates")
    if recency_hours > thresholds.recency_hours:
        reasons.append("no recent readings")
    if metrics.get("geometry_available", 0) == 0:
        reasons.append("unavailable geometry")
    national = station_count >= 1 and coordinate_validity > 0
    forecast = national and history_days >= thresholds.minimum_history_days and completeness >= thresholds.minimum_hourly_completeness
    hyperlocal = forecast and station_count >= thresholds.minimum_hyperlocal_stations and metrics.get("geometry_available", 0) > 0
    intervention = forecast and metrics.get("spatial_feature_availability", 0) > 0 and metrics.get("population_availability", 0) > 0
    return CityReadinessScore(city_id, score, national, forecast, hyperlocal, intervention, components, reasons)
