from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from airview_ml.data.contracts import SourceResult


class Sentinel5PAdapter:
    source = "sentinel5p"
    official_url = "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S5PL2.html"
    token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    def __init__(self, client_id: str | None, client_secret: str | None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    def credentials_status(self) -> SourceResult:
        if not self.client_id or not self.client_secret:
            return SourceResult(
                source=self.source,
                status="credentials_required",
                retrieved_at_utc=datetime.now(timezone.utc),
                official_url=self.official_url,
                credential_requirement="COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET",
                value_kind="provider_derived",
                error="Create an OAuth client in Copernicus Data Space and set both environment variables.",
            )
        return SourceResult(
            source=self.source,
            status="not_ready",
            retrieved_at_utc=datetime.now(timezone.utc),
            official_url=self.official_url,
            credential_requirement="COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET",
            value_kind="provider_derived",
            warnings=["Credentials present; request requires an explicit configured city AOI and date."],
        )

    def access_token(self) -> str:
        if self._access_token and self._token_expires_at and datetime.now(timezone.utc) < self._token_expires_at:
            return self._access_token
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Copernicus credentials are required")
        response = httpx.post(
            self.token_url,
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 300)) - 30)
        return self._access_token

    def validate_statistics(self, aoi_geojson: dict[str, Any], start: str, end: str) -> tuple[dict[str, Any], SourceResult]:
        if not self.client_id or not self.client_secret:
            return {}, self.credentials_status()
        request = self.statistical_request(aoi_geojson, start, end)
        try:
            response = httpx.post(
                "https://sh.dataspace.copernicus.eu/api/v1/statistics",
                json=request,
                headers={"Authorization": f"Bearer {self.access_token()}"},
                timeout=httpx.Timeout(connect=8, read=60, write=30, pool=8),
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            detail = response.text[:800] if "response" in locals() else str(exc)
            return {}, SourceResult(source=self.source, status="failed", retrieved_at_utc=datetime.now(timezone.utc), official_url=self.official_url, credential_requirement="COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET", error=f"{exc}; provider detail: {detail}")
        return payload, SourceResult(source=self.source, status="success", retrieved_at_utc=datetime.now(timezone.utc), row_count=len(payload.get("data", [])) if isinstance(payload, dict) else 0, official_url=self.official_url, credential_requirement="COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET", processing_steps=["OAuth client-credentials authentication", "Copernicus Data Space Statistical API request"])

    @staticmethod
    def statistical_request(aoi_geojson: dict[str, Any], start: str, end: str, collection: str = "sentinel-5p-l2") -> dict[str, Any]:
        return {
            "input": {"bounds": {"geometry": aoi_geojson}, "data": [{"type": collection, "dataFilter": {"timeRange": {"from": start, "to": end}}}]},
            "aggregation": {"timeRange": {"from": start, "to": end}, "aggregationInterval": {"of": "P1D"}, "resx": 0.01, "resy": 0.01, "evalscript": "//VERSION=3\nfunction setup() { return { input: [\"NO2\", \"dataMask\"], output: [{ id: \"default\", bands: 1 }, { id: \"dataMask\", bands: 1 }] }; }\nfunction evaluatePixel(sample) { return { default: [sample.NO2], dataMask: [sample.dataMask] }; }"},
            "calculations": {"default": {"statistics": {"default": {"percentiles": {"k": [5, 50, 95]}}}}},
        }
