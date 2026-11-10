"""Security baseline (Phase 4): non-finite numbers refused, missing upstream values never substituted, malformed responses refused.

The NaN tests document a real false-calm path in 0.2.0: a NaN rain rate passed the sign check. At one endpoint it was silently
dropped (``nan >= x`` is False, so the other endpoint's rain was used and the result looked fully measured); at both endpoints the
exposure ratio was NaN, which ``calculate_exposure`` classified "low".
"""
import math
from unittest.mock import MagicMock, patch

import pytest

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance, WeatherObservation, calculate_exposure
from aei_mw_exposure.infrastructure import ised
from aei_mw_exposure.infrastructure._arcgis import query_arcgis_layer
from aei_mw_exposure.providers import eccc
from aei_mw_exposure.providers.open_meteo import OpenMeteoProvider, ProviderResponseError

A = MicrowaveSite(id="a", name="A", latitude=43.65, longitude=-79.38, provenance=Provenance.DEMO)
B = MicrowaveSite(id="b", name="B", latitude=43.70, longitude=-79.30, provenance=Provenance.DEMO)


def _obs(rain, site="a", **kw):
    return WeatherObservation(latitude=43.6, longitude=-79.4, timestamp="t", rain_rate_mm_h=rain, source="test", site_id=site, **kw)


def _resp(payload):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = payload
    return r


# --- domain types ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "5", None, True])
def test_weather_observation_refuses_non_finite_rain(bad):
    with pytest.raises(ValueError, match="rain_rate_mm_h"):
        _obs(bad)


@pytest.mark.parametrize("field", ["temperature_c", "wind_speed_kmh"])
def test_weather_observation_refuses_non_finite_optional_fields(field):
    with pytest.raises(ValueError, match=field):
        _obs(1.0, **{field: math.nan})
    assert getattr(_obs(1.0, **{field: None}), field) is None  # None stays allowed


@pytest.mark.parametrize("field", ["frequency_ghz", "fade_margin_db"])
@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_link_refuses_non_finite_frequency_and_margin(field, bad):
    args = dict(id="l", site_a=A, site_b=B, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)
    args[field] = bad
    with pytest.raises(ValueError, match=field):
        MicrowaveLink(**args)


@pytest.mark.parametrize("kw", [dict(moderate_threshold=math.nan), dict(high_threshold=math.nan), dict(moderate_threshold=-0.1),
                                dict(moderate_threshold=0.8, high_threshold=0.5)])
def test_exposure_refuses_unusable_thresholds(kw):
    link = MicrowaveLink(id="l", site_a=A, site_b=B, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)
    with pytest.raises(ValueError, match="threshold"):
        calculate_exposure(link, {"a": _obs(10.0), "b": _obs(5.0, site="b")}, **kw)


def test_valid_exposure_unchanged():
    link = MicrowaveLink(id="l", site_a=A, site_b=B, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)
    e = calculate_exposure(link, {"a": _obs(25.0), "b": _obs(5.0, site="b")})
    assert math.isfinite(e.exposure_ratio) and e.severity in ("low", "moderate", "high")


# --- Open-Meteo provider ---------------------------------------------------------------------------------------------------------------------

GOOD = {"current": {"time": "2026-11-10T12:00", "rain": 1.5, "precipitation": 1.5, "temperature_2m": 4.0, "wind_speed_10m": 12.0},
        "hourly": {"time": ["2026-11-10T12:00", "2026-11-10T13:00"], "precipitation": [1.5, 0.0]}}


def test_open_meteo_valid_response_unchanged():
    with patch("requests.get", return_value=_resp(GOOD)):
        obs = OpenMeteoProvider().get_current(A)
        fc = OpenMeteoProvider().get_forecast(A, hours=2)
    assert obs.rain_rate_mm_h == 1.5 and obs.temperature_c == 4.0
    assert [o.rain_rate_mm_h for o in fc] == [1.5, 0.0]


def test_open_meteo_zero_rain_still_falls_back_to_precipitation_as_before():
    payload = {"current": {"time": "t", "rain": 0.0, "precipitation": 0.4}}
    with patch("requests.get", return_value=_resp(payload)):
        assert OpenMeteoProvider().get_current(A).rain_rate_mm_h == 0.4
    payload = {"current": {"time": "t", "rain": 0.0, "precipitation": None}}
    with patch("requests.get", return_value=_resp(payload)):
        assert OpenMeteoProvider().get_current(A).rain_rate_mm_h == 0.0  # a real 0.0 reading is kept


def test_open_meteo_missing_rain_is_not_read_as_zero():
    payload = {"current": {"time": "t", "rain": None, "precipitation": None}}
    with patch("requests.get", return_value=_resp(payload)), pytest.raises(ProviderResponseError, match="no rain rate was substituted"):
        OpenMeteoProvider().get_current(A)


def test_open_meteo_missing_forecast_hour_is_not_read_as_zero():
    payload = {"current": {"time": "2026-11-10T12:00"}, "hourly": {"time": ["2026-11-10T12:00", "2026-11-10T13:00"], "precipitation": [1.0, None]}}
    with patch("requests.get", return_value=_resp(payload)), pytest.raises(ProviderResponseError, match="not read as 0"):
        OpenMeteoProvider().get_forecast(A, hours=2)


@pytest.mark.parametrize("payload", [[], "x", {"current": None}, {"current": {"rain": 1.0}}, {"current": {"time": "t", "rain": math.nan}},
                                     {"current": {"time": "t", "rain": "1.0"}}])
def test_open_meteo_malformed_current_refused(payload):
    with patch("requests.get", return_value=_resp(payload)), pytest.raises(ProviderResponseError):
        OpenMeteoProvider().get_current(A)


def test_open_meteo_misaligned_hourly_series_refused():
    payload = {"current": {"time": "t"}, "hourly": {"time": ["t1", "t2"], "precipitation": [1.0]}}
    with patch("requests.get", return_value=_resp(payload)), pytest.raises(ProviderResponseError, match="do not line up"):
        OpenMeteoProvider().get_forecast(A)


def test_provider_error_is_a_value_error():
    assert issubclass(ProviderResponseError, ValueError)


# --- ECCC ------------------------------------------------------------------------------------------------------------------------------------

def _swob(name, lon, lat, pcpn):
    return {"geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"stn_nam-value": name, "date_tm-value": "2026-11-10T12:00:00Z", "pcpn_amt_pst1hr": pcpn}}


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1.0, "2.0"])
def test_station_with_unusable_precipitation_counts_as_not_reporting(bad):
    with patch("requests.get", return_value=_resp({"features": [_swob("S", -79.4, 43.65, bad)]})):
        obs, _dist, reports = eccc.find_nearest_station(43.65, -79.40)
    assert reports is False and obs.rain_rate_mm_h == 0.0  # placeholder, flagged by reports_precipitation, as documented


def test_station_with_broken_geometry_is_skipped_not_fatal():
    broken = {"geometry": {"coordinates": [math.nan, 43.6]}, "properties": {"stn_nam-value": "BROKEN", "date_tm-value": "2026-11-10T12:00:00Z"}}
    with patch("requests.get", return_value=_resp({"features": [broken, _swob("GOOD", -79.4, 43.65, 1.0)]})):
        obs, _dist, reports = eccc.find_nearest_station(43.65, -79.40)
    assert "GOOD" in obs.source and reports is True


def test_station_query_refuses_non_object_response():
    with patch("requests.get", return_value=_resp(["not", "an", "object"])), pytest.raises(ValueError):
        eccc.find_nearest_station(43.65, -79.40)


@pytest.mark.parametrize("value", [math.nan, math.inf, -2.0, "3"])
def test_radar_unusable_value_is_no_data(value):
    with patch("requests.get", return_value=_resp({"features": [{"properties": {"value": value, "time": "t"}}]})):
        assert eccc.get_radar_precipitation(43.65, -79.40) is None


def test_radar_non_object_response_is_no_data():
    with patch("requests.get", return_value=_resp([1, 2])):
        assert eccc.get_radar_precipitation(43.65, -79.40) is None


# --- ArcGIS infrastructure -----------------------------------------------------------------------------------------------------------------

def test_ised_row_with_non_finite_or_out_of_range_coordinates_is_skipped():
    rows = [{"attributes": {"OBJECTID": 1}, "geometry": {"x": math.nan, "y": 43.6}},
            {"attributes": {"OBJECTID": 2}, "geometry": {"x": -79.4, "y": 123.0}},
            {"attributes": {"OBJECTID": 3, "LICENSEE": "X"}, "geometry": {"x": -79.4, "y": 43.6}}]
    sites, skipped = ised.load_sites(rows)
    assert [s.id for s in sites] == ["ised-3"]
    assert len(skipped) == 2 and all("no coordinates" in m for m in skipped)


def test_arcgis_non_object_response_and_non_dict_features():
    with patch("requests.get", return_value=_resp([1])), pytest.raises(RuntimeError, match="not a JSON object"):
        query_arcgis_layer("https://example.invalid/query", (0, 0, 1, 1))
    with patch("requests.get", return_value=_resp({"features": [{"attributes": {}}, "junk", 7]})):
        assert len(query_arcgis_layer("https://example.invalid/query", (0, 0, 1, 1)).features) == 1
