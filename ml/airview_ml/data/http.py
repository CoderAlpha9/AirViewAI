import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class SourceRequestError(RuntimeError):
    pass


class CachedHttpClient:
    def __init__(self, cache_root: Path, timeout_seconds: float = 30.0) -> None:
        self.cache_root = cache_root
        self.timeout_seconds = timeout_seconds

    @property
    def timeout(self) -> httpx.Timeout:
        """Use explicit phase limits so slow public APIs fail predictably."""
        return httpx.Timeout(connect=min(self.timeout_seconds, 8), read=self.timeout_seconds, write=self.timeout_seconds, pool=min(self.timeout_seconds, 8))

    def _cache_path(self, source: str, url: str, params: dict[str, Any] | None) -> Path:
        identity = json.dumps({"url": url, "params": params or {}}, sort_keys=True, default=str)
        digest = hashlib.sha256(identity.encode()).hexdigest()
        return self.cache_root / source / "http" / f"{digest}.json"

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, SourceRequestError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def get_json(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> tuple[Any, Path, bool]:
        cache_path = self._cache_path(source, url, params)
        if cache_path.is_file() and not force:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached.get("payload", cached), cache_path, True
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                raise SourceRequestError(
                    f"{source} request rejected with HTTP {exc.response.status_code}: {exc.response.text[:300]}"
                ) from exc
            raise
        payload = response.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "url": str(response.url),
                    "payload": payload,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return payload, cache_path, False

    def get_text(
        self,
        source: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> tuple[str, Path, bool]:
        cache_path = self._cache_path(source, url, None).with_suffix(".txt")
        if cache_path.is_file() and not force:
            return cache_path.read_text(encoding="utf-8"), cache_path, True
        response = httpx.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(response.text, encoding="utf-8")
        return response.text, cache_path, False

    def post_json(
        self,
        source: str,
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> tuple[Any, Path, bool]:
        cache_path = self._cache_path(source, url, data)
        if cache_path.is_file() and not force:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached.get("payload", cached), cache_path, True
        response = httpx.post(url, data=data, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "url": str(response.url),
                    "payload": payload,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return payload, cache_path, False
