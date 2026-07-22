import json
from pathlib import Path

import joblib
import pandas as pd

from airview_ml.forecasting.global_residual import FEATURES


def test_six_global_residual_artifacts_support_unseen_coordinates() -> None:
    root = Path(__file__).resolve().parents[2]
    sample = {feature: 0.0 for feature in FEATURES}
    sample.update({"camps_current": 55, "camps_target": 62, "latitude": 12.97, "longitude": 77.59})
    for pollutant in ("pm2_5", "pm10"):
        for horizon in (24, 48, 72):
            folder = root / "models" / "forecasting" / "global_residual" / pollutant / str(horizon)
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            schema = json.loads((folder / "feature_schema.json").read_text(encoding="utf-8"))
            model = joblib.load(folder / "model.joblib")
            prediction = model.predict(pd.DataFrame([sample]))
            assert len(prediction) == 1
            assert metadata["supports_unseen_cities"] is True
            assert metadata["horizon"] == horizon
            assert metadata["historical_cams_values_present"] is False
            assert (
                metadata["training_target_formula"]
                == "target_residual(t,h) = observed_station(t+h) - observed_station(t)"
            )
            assert metadata["features"] == FEATURES == schema
            assert type(model).__name__ == "Pipeline"
            assert type(model.named_steps["impute"]).__name__ == "SimpleImputer"
            assert type(model.named_steps["regressor"]).__name__ == "HistGradientBoostingRegressor"
