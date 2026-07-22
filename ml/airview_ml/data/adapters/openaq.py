import gzip
import io
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from typing import Any

import pandas as pd

from airview_ml.data.contracts import SourceResult
from airview_ml.data.http import CachedHttpClient
from airview_ml.data.normalization import normalise_pollutant
from airview_ml.data.units import convert_pollutant


class OpenAQAdapter:
    source = "openaq"
    api_url = "https://api.openaq.org/v3"
    archive_url = "https://openaq-data-archive.s3.amazonaws.com"
    official_url = "https://docs.openaq.org/"

    def __init__(self, client: CachedHttpClient, api_key: str | None) -> None:
        self.client = client
        self.api_key = api_key

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    def fetch_locations_india(self, limit: int = 1_000) -> tuple[list[dict[str, Any]], SourceResult]:
        if not self.api_key:
            return [], SourceResult(
                source=self.source,
                status="credentials_required",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="OPENAQ_API_KEY",
                error="Set OPENAQ_API_KEY to discover locations and sensors through OpenAQ v3.",
            )
        page = 1
        results: list[dict[str, Any]] = []
        try:
            while True:
                payload, cache_path, _ = self.client.get_json(
                    self.source,
                    f"{self.api_url}/locations",
                    params={"iso": "IN", "limit": limit, "page": page},
                    headers=self.headers,
                )
                items = payload.get("results", [])
                results.extend(items)
                meta = payload.get("meta", {})
                if len(items) < limit or page >= int(meta.get("found", 0) / limit) + 1:
                    break
                page += 1
        except Exception as exc:
            return [], SourceResult(
                source=self.source,
                status="failed",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="OPENAQ_API_KEY",
                error=str(exc),
            )
        return results, SourceResult(
            source=self.source,
            status="success",
            retrieved_at_utc=datetime.now(timezone.utc),
            row_count=len(results),
            cache_path=str(cache_path),
            geographic_coverage="India locations exposed by OpenAQ v3",
            official_url=self.official_url,
            credential_requirement="OPENAQ_API_KEY",
            processing_steps=["OpenAQ v3 paginated location discovery"],
        )

    def probe_archive(self) -> SourceResult:
        try:
            _, cache_path, _ = self.client.get_text(
                "openaq_archive", f"{self.archive_url}/?list-type=2&prefix=records/csv.gz/&delimiter=/&max-keys=1"
            )
        except Exception as exc:
            return SourceResult(
                source="openaq_archive",
                status="failed",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url="https://docs.openaq.org/aws/about",
                error=str(exc),
            )
        return SourceResult(
            source="openaq_archive",
            status="success",
            retrieved_at_utc=datetime.now(timezone.utc),
            cache_path=str(cache_path),
            geographic_coverage="Public unsigned S3 archive reachable; India partitions require discovered location IDs",
            official_url="https://docs.openaq.org/aws/about",
            licence="Provider-specific licences preserved in OpenAQ metadata",
            processing_steps=["unsigned S3 index probe"],
        )

    @staticmethod
    def archive_path(location_id: int, year: int, month: int, day: int) -> str:
        return (
            f"records/csv.gz/locationid={location_id}/year={year}/month={month:02d}/"
            f"location-{location_id}-{year}{month:02d}{day:02d}.csv.gz"
        )

    @staticmethod
    def parse_archive_path(path: str) -> dict[str, int]:
        parts = PurePosixPath(path).parts
        fields: dict[str, int] = {}
        for item in parts:
            if "=" in item:
                key, value = item.split("=", 1)
                fields[key] = int(value)
        if not {"locationid", "year", "month"}.issubset(fields):
            raise ValueError(f"Not an OpenAQ archive partition path: {path}")
        return fields

    @staticmethod
    def decompress_csv(content: bytes) -> pd.DataFrame:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            return pd.read_csv(stream)

    def list_archive_files(self, location_id: int, start: date, end: date) -> list[dict[str, Any]]:
        keys: list[dict[str, Any]] = []
        # One yearly S3 list is normally enough (daily files are <1000/year) and
        # is dramatically cheaper than probing every month during an India audit.
        for year in range(start.year, end.year + 1):
            prefix = f"records/csv.gz/locationid={location_id}/year={year}/"
            for item in self._list_s3(prefix):
                key = item.get("key")
                if key:
                    day = _archive_day(key)
                    if day and start <= day <= end:
                        keys.append({"key": key, "size": int(item.get("size") or 0), "date": day.isoformat(), "etag": item.get("etag")})
        return keys

    def audit_archive_location(self, location_id: int, start: date, end: date, location: dict[str, Any] | None = None) -> dict[str, Any]:
        """Inspect only S3 listings. No archive object is downloaded by this operation."""
        files = self.list_archive_files(location_id, start, end)
        months = sorted({item["date"][:7] for item in files})
        sensors = (location or {}).get("sensors", [])
        pollutants = sorted({str((sensor.get("parameter") or {}).get("name") or "").lower() for sensor in sensors if (sensor.get("parameter") or {}).get("name")})
        return {
            "location_id": location_id,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "available_years": sorted({month[:4] for month in months}),
            "available_months": months,
            "supported_pollutants_from_provider_metadata": pollutants,
            "most_recent_file": max(files, key=lambda item: item["date"], default=None),
            "estimated_file_count": len(files),
            "estimated_size_bytes": sum(int(item["size"]) for item in files),
            "index_status": "success",
        }

    def _list_s3(self, prefix: str) -> list[dict[str, str | int | None]]:
        """List an S3 prefix completely, following continuation tokens deterministically."""
        items: list[dict[str, str | int | None]] = []
        token: str | None = None
        while True:
            suffix = f"?list-type=2&prefix={prefix}&max-keys=1000"
            if token:
                suffix += f"&continuation-token={token}"
            text, _, _ = self.client.get_text("openaq_archive", f"{self.archive_url}/{suffix}")
            root = ET.fromstring(text)
            namespace = "{http://s3.amazonaws.com/doc/2006-03-01/}"
            for node in root.findall(f"{namespace}Contents"):
                items.append({"key": node.findtext(f"{namespace}Key"), "size": int(node.findtext(f"{namespace}Size") or 0), "etag": node.findtext(f"{namespace}ETag")})
            truncated = root.findtext(f"{namespace}IsTruncated") == "true"
            token = root.findtext(f"{namespace}NextContinuationToken")
            if not truncated or not token:
                return items

    def download_archive_file(self, key: str, expected_size: int | None = None) -> tuple[bytes, str]:
        url = f"{self.archive_url}/{key}"
        path = self.client.cache_root / "openaq_archive" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and (expected_size is None or path.stat().st_size == expected_size):
            content = path.read_bytes()
            self.decompress_csv(content)  # verified cache entries are safe to resume from
            return content, str(path)
        partial = path.with_suffix(path.suffix + ".partial")
        response = __import__("httpx").get(url, timeout=__import__("httpx").Timeout(connect=8, read=60, write=60, pool=8))
        response.raise_for_status()
        partial.write_bytes(response.content)
        if expected_size is not None and partial.stat().st_size != expected_size:
            raise RuntimeError(f"archive size mismatch for {key}: expected {expected_size}, got {partial.stat().st_size}")
        self.decompress_csv(partial.read_bytes())  # gzip and CSV integrity validation before promotion
        partial.replace(path)
        return response.content, str(path)

    @staticmethod
    def archive_sensor_hourly(frame: pd.DataFrame, mapped_location: dict[str, Any]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for record in frame.to_dict("records"):
            pollutant = normalise_pollutant(record.get("parameter"))
            if not pollutant:
                continue
            value = float(record["value"]) if pd.notna(record.get("value")) else None
            conversion = convert_pollutant(value, record.get("units"), pollutant)
            timestamp = pd.to_datetime(record.get("datetime"), utc=True, errors="coerce")
            if pd.isna(timestamp):
                continue
            rows.append({"city_id": mapped_location.get("city_id"), "state_id": mapped_location.get("state"), "station_id": mapped_location["station_id"], "station_name": mapped_location.get("station_name"), "sensor_id": f"openaq-{record.get('sensors_id')}", "timestamp_utc": timestamp, "pollutant": pollutant, "value": conversion.value_canonical, "unit": conversion.unit_canonical, "value_original": value, "unit_original": record.get("units"), "latitude": record.get("lat"), "longitude": record.get("lon"), "source": "openaq_archive", "provider": "OpenAQ", "quality_flags": conversion.flags, "provenance_id": mapped_location["location_id"]})
        return pd.DataFrame(rows)


def _archive_day(key: str) -> date | None:
    try:
        stamp = key.rsplit("-", 1)[-1].replace(".csv.gz", "")
        return date.fromisoformat(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}")
    except (IndexError, ValueError):
        return None
