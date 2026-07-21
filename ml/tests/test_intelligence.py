from airview_ml.intelligence.core import (
    bearing,
    distance_decay,
    rain_attenuation,
    stagnation,
    temporal_decay,
    tier,
    wind_alignment,
)


def test_relative_transport_primitives_are_bounded():
    assert 0 <= bearing(28, 77, 29, 77) <= 360
    assert distance_decay(0) == 1
    assert 0 < temporal_decay(12) < 1
    assert rain_attenuation(5) < 1
    assert wind_alignment(0, 0) == 1


def test_stagnation_and_insufficient_evidence():
    assert stagnation(0, 0) > stagnation(5, 0)
    assert tier(.9, .2) == "Insufficient evidence"
