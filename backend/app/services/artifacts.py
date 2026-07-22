"""Small mtime-aware cache for report and Parquet artifacts.

The dashboard uses this store so requests do not repeatedly parse large files.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pandas as pd


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.RLock()
        self._json: dict[Path, tuple[int, Any]] = {}
        self._frames: dict[Path, tuple[int, pd.DataFrame]] = {}

    def _path(self, relative: str | Path) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    def json(self, relative: str | Path, default: Any | None = None) -> Any:
        path = self._path(relative)
        if not path.is_file():
            if default is not None:
                return default
            raise FileNotFoundError(path)
        stamp = path.stat().st_mtime_ns
        with self._lock:
            cached = self._json.get(path)
            if cached and cached[0] == stamp:
                return cached[1]
            value = json.loads(path.read_text(encoding="utf-8"))
            self._json[path] = (stamp, value)
            return value

    def parquet(self, relative: str | Path) -> pd.DataFrame:
        path = self._path(relative)
        if not path.is_file():
            raise FileNotFoundError(path)
        stamp = path.stat().st_mtime_ns
        with self._lock:
            cached = self._frames.get(path)
            if cached and cached[0] == stamp:
                return cached[1]
            frame = pd.read_parquet(path)
            self._frames[path] = (stamp, frame)
            return frame


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
artifacts = ArtifactStore(REPOSITORY_ROOT)
