"""Causal station-receptor FIRMS feature generation from the local event archive."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed" / "india"
REPORTS = ROOT / "outputs" / "reports"
WINDOWS = (6, 12, 24, 48, 72, 168)
BANDS = (25, 50, 100, 300)


def _distance(lat: np.ndarray, lon: np.ndarray, station_lat: float, station_lon: float) -> np.ndarray:
    lat1, lon1 = np.radians(station_lat), np.radians(station_lon)
    lat2, lon2 = np.radians(lat), np.radians(lon)
    value = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(value))


def _bearing(lat: np.ndarray, lon: np.ndarray, station_lat: float, station_lon: float) -> np.ndarray:
    delta = np.radians(lon - station_lon)
    lat2, lat1 = np.radians(lat), np.radians(station_lat)
    return (np.degrees(np.arctan2(np.sin(delta) * np.cos(lat2), np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(delta))) + 360) % 360


def _issues() -> pd.DataFrame:
    attribution = pd.read_parquet(PROCESSED / "source_attribution" / "source_attribution.parquet")
    times = attribution[["city_id", "station_id", "timestamp_utc", "latitude", "longitude"]].drop_duplicates()
    weather = pd.read_parquet(PROCESSED / "station_hourly_features.parquet")
    weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True)
    return times.merge(weather[["station_id", "timestamp_utc", "wind_speed_10m", "wind_direction_10m"]], on=["station_id", "timestamp_utc"], how="left").sort_values(["city_id", "timestamp_utc"])


def build() -> pd.DataFrame:
    events = pd.read_parquet(PROCESSED / "firms_events.parquet")
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    issues = _issues()
    records: list[dict[str, object]] = []
    for (city, station), group in issues.groupby(["city_id", "station_id"], sort=False):
        first = group.iloc[0]
        local = events[(events.latitude.between(first.latitude - 3, first.latitude + 3)) & (events.longitude.between(first.longitude - 3, first.longitude + 3))].copy()
        distances = _distance(local.latitude.to_numpy(), local.longitude.to_numpy(), first.latitude, first.longitude)
        local = local.assign(distance_km=distances)
        local = local[local.distance_km <= 300].sort_values("timestamp_utc").reset_index(drop=True)
        bearings = _bearing(local.latitude.to_numpy(), local.longitude.to_numpy(), first.latitude, first.longitude)
        timestamps = local.timestamp_utc.to_numpy(dtype="datetime64[ns]")
        for issue in group.itertuples(index=False):
            result: dict[str, object] = {"city_id": city, "station_id": station, "timestamp_utc": issue.timestamp_utc, "latitude": issue.latitude, "longitude": issue.longitude, "wind_speed_10m": issue.wind_speed_10m, "wind_direction_10m": issue.wind_direction_10m, "firms_data_available": True}
            issue_time = issue.timestamp_utc.to_datetime64()
            for hours in WINDOWS:
                start = issue_time - np.timedelta64(hours, "h")
                left, right = np.searchsorted(timestamps, start, side="left"), np.searchsorted(timestamps, issue_time, side="right")
                subset = local.iloc[left:right]
                distance = subset.distance_km.to_numpy()
                frp = subset.fire_radiative_power.fillna(0).to_numpy(dtype=float)
                age = (issue.timestamp_utc - subset.timestamp_utc).dt.total_seconds().to_numpy() / 3600 if len(subset) else np.array([])
                align = np.maximum(0, np.cos(np.radians(np.abs((bearings[left:right] - float(issue.wind_direction_10m if pd.notna(issue.wind_direction_10m) else 0) + 180) % 360 - 180)))) if len(subset) and pd.notna(issue.wind_direction_10m) else np.zeros(len(subset))
                result[f"firms_count_{hours}h"] = int(len(subset))
                result[f"firms_frp_{hours}h"] = float(frp.sum())
                result[f"firms_nearest_km_{hours}h"] = float(distance.min()) if len(distance) else np.nan
                result[f"firms_max_confidence_{hours}h"] = float(pd.to_numeric(subset.confidence, errors="coerce").max()) if len(subset) else np.nan
                result[f"firms_upwind_count_{hours}h"] = int((align > 0.5).sum())
                result[f"firms_upwind_frp_{hours}h"] = float(frp[align > 0.5].sum())
                result[f"firms_wind_aligned_influence_{hours}h"] = float((frp * align * np.exp(-distance / 100)).sum())
                result[f"firms_event_age_weighted_influence_{hours}h"] = float((frp * np.exp(-age / 24) * np.exp(-distance / 100)).sum()) if len(subset) else 0.0
                for band in BANDS:
                    mask = distance <= band
                    result[f"firms_count_{hours}h_{band}km"] = int(mask.sum())
                    result[f"firms_frp_{hours}h_{band}km"] = float(frp[mask].sum())
            records.append(result)
    output = pd.DataFrame(records)
    output.to_parquet(PROCESSED / "firms_temporal_features.parquet", index=False)
    coverage = float((output["firms_count_24h"] > 0).mean()) if len(output) else 0.0
    (REPORTS / "firms_temporal_feature_report.json").write_text(json.dumps({"status": "success", "row_count": len(output), "issue_timestamp_count": len(output), "cities": sorted(output.city_id.unique().tolist()), "stations": sorted(output.station_id.unique().tolist()), "windows_hours": list(WINDOWS), "distance_bands_km": list(BANDS), "percentage_24h_with_firms_evidence": round(coverage * 100, 4), "causality": "events are selected only where event timestamp_utc <= intelligence issue timestamp_utc"}, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    build()
