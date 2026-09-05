import pytest

from aei_mw_exposure import WeatherObservation, peak_rain


def make_obs(rain: float, timestamp: str = "t"):
    return WeatherObservation(latitude=0.0, longitude=0.0, timestamp=timestamp, rain_rate_mm_h=rain, source="test-fixture")


def test_negative_rain_rejected():
    with pytest.raises(ValueError):
        make_obs(-1.0)


def test_optional_fields_default_to_none():
    obs = make_obs(0.0)
    assert obs.temperature_c is None
    assert obs.wind_speed_kmh is None
    assert obs.site_id is None
    assert obs.fetched_at is None


def test_peak_rain_picks_the_max():
    obs = [make_obs(2.0, "t0"), make_obs(9.5, "t1"), make_obs(4.0, "t2")]
    peak = peak_rain(obs)
    assert peak.rain_rate_mm_h == 9.5
    assert peak.timestamp == "t1"


def test_peak_rain_empty_raises():
    with pytest.raises(ValueError):
        peak_rain([])
