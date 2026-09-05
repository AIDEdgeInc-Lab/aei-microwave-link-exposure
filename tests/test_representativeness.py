import pytest

from aei_mw_exposure import MicrowaveSite, Provenance, WeatherObservation
from aei_mw_exposure.representativeness import (
    DEFAULT_DISAGREEMENT_THRESHOLD_MM_H,
    DEFAULT_MAX_STATION_DISTANCE_KM,
    assess_representativeness,
)


def make_site():
    return MicrowaveSite(id="s1", name="Test Site", latitude=44.06, longitude=-79.46, provenance=Provenance.REAL, source="test")


def make_obs(rain_rate: float, lat=44.06, lon=-79.46):
    return WeatherObservation(latitude=lat, longitude=lon, timestamp="2026-09-04T20:00:00Z", rain_rate_mm_h=rain_rate, source="test")


def test_no_station_is_insufficient_evidence():
    r = assess_representativeness(site=make_site())
    assert r.level == "insufficient_evidence"
    assert r.nearest_station is None
    assert r.station_distance_km is None
    assert r.precipitation_difference_mm_h is None


def test_close_station_agreeing_with_model_is_consistent():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(5.0),
        station_distance_km=8.0,
        model_observation=make_obs(6.0),
    )
    assert r.level == "consistent"
    assert r.precipitation_difference_mm_h == 1.0


def test_close_station_disagreeing_with_model_is_moderate():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(1.0),
        station_distance_km=8.0,
        model_observation=make_obs(9.0),
    )
    assert r.level == "moderate_disagreement"
    assert r.precipitation_difference_mm_h == 8.0


def test_far_station_and_disagreement_is_high():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(1.0),
        station_distance_km=DEFAULT_MAX_STATION_DISTANCE_KM + 20,
        model_observation=make_obs(9.0),
    )
    assert r.level == "high_disagreement"


def test_far_station_with_agreeing_values_is_still_moderate():
    """Distance alone is grounds for caution, even if the two values
    happen to agree right now -- the label reflects evidence quality, not
    just numeric agreement."""
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(3.0),
        station_distance_km=DEFAULT_MAX_STATION_DISTANCE_KM + 5,
        model_observation=make_obs(3.2),
    )
    assert r.level == "moderate_disagreement"


def test_exact_threshold_difference_is_not_disagreement():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(1.0),
        station_distance_km=10.0,
        model_observation=make_obs(1.0 + DEFAULT_DISAGREEMENT_THRESHOLD_MM_H),
    )
    assert r.precipitation_difference_mm_h == DEFAULT_DISAGREEMENT_THRESHOLD_MM_H
    assert r.level == "consistent"  # strictly greater-than is required to flag disagreement


def test_station_without_precipitation_field_is_insufficient_evidence():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(0.0),  # placeholder value -- must be ignored
        station_distance_km=10.0,
        station_reports_precipitation=False,
        model_observation=make_obs(9.0),
    )
    assert r.level == "insufficient_evidence"
    assert r.precipitation_difference_mm_h is None
    assert "does not publish" in r.note


def test_missing_model_observation_is_insufficient_evidence():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(1.0),
        station_distance_km=10.0,
        model_observation=None,
    )
    assert r.level == "insufficient_evidence"
    assert "no model value" in r.note


def test_station_distance_required_when_station_given():
    with pytest.raises(ValueError):
        assess_representativeness(site=make_site(), nearest_station=make_obs(1.0))


def test_radar_observation_is_carried_but_does_not_affect_level():
    """Radar is displayed as a third piece of evidence but is not folded
    into the station-vs-model classification -- a deliberate scope limit,
    stated here so a future change to that rule is a conscious decision."""
    without_radar = assess_representativeness(
        site=make_site(), nearest_station=make_obs(5.0), station_distance_km=8.0, model_observation=make_obs(5.5)
    )
    with_radar = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(5.0),
        station_distance_km=8.0,
        model_observation=make_obs(5.5),
        radar_observation=make_obs(40.0),  # deliberately wildly different
    )
    assert without_radar.level == with_radar.level
    assert with_radar.radar_observation is not None
    assert with_radar.radar_observation.rain_rate_mm_h == 40.0


def test_thresholds_are_overridable():
    r = assess_representativeness(
        site=make_site(),
        nearest_station=make_obs(1.0),
        station_distance_km=8.0,
        model_observation=make_obs(1.5),
        disagreement_threshold_mm_h=0.1,
    )
    assert r.level == "moderate_disagreement"  # a 0.5 mm/h diff now exceeds the tightened threshold
