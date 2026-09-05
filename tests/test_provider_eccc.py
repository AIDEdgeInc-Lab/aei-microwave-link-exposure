"""Tests use mocked `requests.get` responses shaped like the real
SWOB-Realtime / radar WMS payloads (verified live during this project's
research) -- no network access in tests."""

from unittest.mock import MagicMock, patch

from aei_mw_exposure.providers import eccc


def _fake_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def _swob_feature(name: str, lon: float, lat: float, ts: str, pcpn=0.0):
    props = {"stn_nam-value": name, "date_tm-value": ts}
    if pcpn is not None:
        props["pcpn_amt_pst1hr"] = pcpn
    return {"geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def test_finds_the_closest_of_several_candidate_stations():
    # Newmarket-ish query point; station B is geometrically closer than A or C.
    features = [
        _swob_feature("FAR STATION", -80.2, 44.6, "2026-09-04T20:00:00.000Z", pcpn=1.0),
        _swob_feature("NEAR STATION", -79.50, 44.10, "2026-09-04T20:00:00.000Z", pcpn=2.0),
        _swob_feature("MID STATION", -79.9, 44.3, "2026-09-04T20:00:00.000Z", pcpn=3.0),
    ]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        result = eccc.find_nearest_station(44.06, -79.46, search_radius_km=100.0)
    assert result is not None
    obs, distance, reports_precip = result
    assert "NEAR STATION" in obs.source
    assert reports_precip is True
    assert obs.rain_rate_mm_h == 2.0


def test_dedupes_repeated_readings_and_keeps_the_most_recent():
    features = [
        _swob_feature("ONE STATION", -79.50, 44.10, "2026-09-04T19:00:00.000Z", pcpn=1.0),
        _swob_feature("ONE STATION", -79.50, 44.10, "2026-09-04T20:00:00.000Z", pcpn=5.0),  # newer
        _swob_feature("ONE STATION", -79.50, 44.10, "2026-09-04T19:30:00.000Z", pcpn=2.0),
    ]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        result = eccc.find_nearest_station(44.06, -79.46, search_radius_km=100.0)
    obs, distance, reports_precip = result
    assert obs.timestamp == "2026-09-04T20:00:00.000Z"
    assert obs.rain_rate_mm_h == 5.0


def test_station_beyond_search_radius_is_excluded():
    features = [_swob_feature("DISTANT", -85.0, 48.0, "2026-09-04T20:00:00.000Z", pcpn=1.0)]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        result = eccc.find_nearest_station(44.06, -79.46, search_radius_km=50.0)
    assert result is None


def test_station_without_precipitation_field_reports_false():
    features = [_swob_feature("NO PRECIP FIELD", -79.50, 44.10, "2026-09-04T20:00:00.000Z", pcpn=None)]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        result = eccc.find_nearest_station(44.06, -79.46, search_radius_km=100.0)
    obs, distance, reports_precip = result
    assert reports_precip is False
    assert obs.rain_rate_mm_h == 0.0  # placeholder only -- reports_precip is the authoritative signal


def test_no_stations_in_window_returns_none():
    with patch("requests.get", return_value=_fake_response({"features": []})):
        result = eccc.find_nearest_station(44.06, -79.46)
    assert result is None


def test_radar_returns_observation_when_value_present():
    payload = {
        "features": [
            {
                "properties": {
                    "value": 4.5,
                    "class": "Light",
                    "time": "2026-09-04T21:00:00Z",
                }
            }
        ]
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        obs = eccc.get_radar_precipitation(44.06, -79.46)
    assert obs is not None
    assert obs.rain_rate_mm_h == 4.5
    assert "radar-estimated" in obs.source.lower()


def test_radar_zero_value_is_a_real_reading_not_missing():
    payload = {"features": [{"properties": {"value": 0, "class": "Undetected", "time": "2026-09-04T21:00:00Z"}}]}
    with patch("requests.get", return_value=_fake_response(payload)):
        obs = eccc.get_radar_precipitation(44.06, -79.46)
    assert obs is not None
    assert obs.rain_rate_mm_h == 0.0


def test_radar_no_features_returns_none():
    with patch("requests.get", return_value=_fake_response({"features": []})):
        obs = eccc.get_radar_precipitation(44.06, -79.46)
    assert obs is None


def test_radar_request_failure_returns_none_not_an_exception():
    with patch("requests.get", side_effect=ConnectionError("boom")):
        obs = eccc.get_radar_precipitation(44.06, -79.46)
    assert obs is None
