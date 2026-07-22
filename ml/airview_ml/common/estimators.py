from typing import Any, Literal

from sklearn.ensemble import HistGradientBoostingRegressor

EstimatorPreference = Literal["auto", "xgboost", "sklearn"]


def create_regressor(
    preference: EstimatorPreference = "auto", random_state: int = 42, **kwargs: Any
) -> Any:
    """Create a forecast regressor, using XGBoost only when requested and available."""
    if preference in {"auto", "xgboost"}:
        try:
            from xgboost import XGBRegressor

            return XGBRegressor(random_state=random_state, **kwargs)
        except ImportError:
            if preference == "xgboost":
                raise RuntimeError(
                    "XGBoost was requested but is not installed. Install airview-ml[xgboost]."
                ) from None

    sklearn_kwargs = {"random_state": random_state, **kwargs}
    return HistGradientBoostingRegressor(**sklearn_kwargs)
