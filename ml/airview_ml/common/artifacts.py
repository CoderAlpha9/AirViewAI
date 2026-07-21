from pathlib import Path
from typing import Any

import joblib


def save_artifact(model: Any, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, destination)
    return destination


def load_artifact(source: Path) -> Any:
    if not source.is_file():
        raise FileNotFoundError(f"Model artifact not found: {source}")
    return joblib.load(source)

