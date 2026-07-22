from sklearn.ensemble import HistGradientBoostingRegressor

from airview_ml.common.estimators import create_regressor


def test_sklearn_fallback_can_be_selected() -> None:
    estimator = create_regressor("sklearn")

    assert isinstance(estimator, HistGradientBoostingRegressor)

