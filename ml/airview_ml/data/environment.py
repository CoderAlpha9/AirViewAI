"""Safe, location-independent dotenv discovery for AirView commands."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from airview_ml.data.config import find_repository_root


def load_environment(root: Path | None = None) -> Path | None:
    """Load the first existing configured dotenv file without replacing process variables."""
    repository = (root or find_repository_root(Path(__file__))).resolve()
    explicit = os.getenv("AIRVIEW_ENV_FILE")
    candidates = [Path(explicit)] if explicit else []
    candidates += [repository / ".env", repository / "backend" / ".env", Path.cwd() / ".env"]
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


def credential_status(root: Path | None = None) -> dict[str, object]:
    path = load_environment(root)
    names = ["DATA_GOV_IN_API_KEY", "OPENAQ_API_KEY", "NASA_FIRMS_MAP_KEY", "COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET"]
    return {"environment_file": str(path) if path else None, "credentials": {name: {"configured": bool(os.getenv(name))} for name in names}}
