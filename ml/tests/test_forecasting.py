from airview_ml.forecasting.aqi import category, sub_index


def test_indian_pm_breakpoints_and_categories() -> None:
    assert sub_index(30, "pm2_5") == 50
    assert sub_index(60, "pm2_5") == 100
    assert sub_index(600, "pm10") == 500
    assert category(301) == "Very Poor"
    assert sub_index(12, "pm2_5", "ppm") is None
