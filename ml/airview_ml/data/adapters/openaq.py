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
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            prefix = f"records/csv.gz/locationid={location_id}/year={year}/month={month:02d}/"
            text, _, _ = self.client.get_text("openaq_archive", f"{self.archive_url}/?list-type=2&prefix={prefix}&max-keys=1000")
            root = ET.fromstring(text)
            for node in root.findall("{http://s3.amazonaws.com/doc/2006-03-01/}Contents"):
                key = node.findtext("{http://s3.amazonaws.com/doc/2006-03-01/}Key")
                size = node.findtext("{http://s3.amazonaws.com/doc/2006-03-01/}Size")
                if key:
                    day = date.fromisoformat(key.rsplit("-", 1)[-1].replace(".csv.gz", "")[:4] + "-" + key.rsplit("-", 1)[-1][4:6] + "-" + key.rsplit("-", 1)[-1][6:8])
                    if start <= day <= end:
                        keys.append({"key": key, "size": int(size or 0), "date": day.isoformat()})
            month += 1
            if month == 13:
                year, month = year + 1, 1
        return keys

    def download_archive_file(self, key: str) -> tuple[bytes, str]:
        url = f"{self.archive_url}/{key}"
        response = __import__("httpx").get(url, timeout=__import__("httpx").Timeout(connect=5, read=30, write=30, pool=5))
        response.raise_for_status()
        path = self.client.cache_root / "openaq_archive" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.stat().st_size != len(response.content):
            path.write_bytes(response.content)
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
