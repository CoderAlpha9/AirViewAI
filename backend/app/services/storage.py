from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


class TabularStorage(Protocol):
    """Boundary for prototype file storage and a future SQLite implementation."""

    def read_records(self, dataset: str) -> list[dict[str, Any]]: ...

    def write_records(self, dataset: str, records: Iterable[dict[str, Any]]) -> None: ...


class CsvStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path_for(self, dataset: str) -> Path:
        if not dataset.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Dataset names may only contain letters, numbers, '-' and '_'")
        return self.root / f"{dataset}.csv"

    def read_records(self, dataset: str) -> list[dict[str, Any]]:
        path = self._path_for(dataset)
        if not path.exists():
            return []
        return pd.read_csv(path).to_dict(orient="records")

    def write_records(self, dataset: str, records: Iterable[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(list(records)).to_csv(self._path_for(dataset), index=False)


class SQLiteStorage:
    """Reserved adapter boundary for later persistence work."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def read_records(self, dataset: str) -> list[dict[str, Any]]:
        raise NotImplementedError("SQLite persistence is planned but not active in this foundation")

    def write_records(self, dataset: str, records: Iterable[dict[str, Any]]) -> None:
        raise NotImplementedError("SQLite persistence is planned but not active in this foundation")

