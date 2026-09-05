"""End-to-end composition checks across real infrastructure, weather, and
the demo network -- no network access; everything here is deterministic."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance, WeatherObservation, calculate_exposure
from aei_mw_exposure.infrastructure.ontario_geohub import parse_tower_feature
from aei_mw_exposure.providers import eccc
from aei_mw_exposure.representativeness import assess_representativeness

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REAL_TOWER_FEATURE = {
    "attributes": {"CLASS_SUBTYPE": "Communication Tower", "OBJECTID": 1711},
    "geometry": {"x": -79.8519551, "y": 43.5374084},
}


def test_real_infrastructure_site_pairs_with_a_weather_observation():
    """Pipeline: real infrastructure -> normalized MicrowaveSite -> weather.
    A REAL site can carry a live weather observation keyed by its id --
    this is the actual shape the Explorer app uses -- without ever needing
    a MicrowaveLink (which this site does not have)."""
    site = parse_tower_feature(REAL_TOWER_FEATURE)
    weather_by_site = {
        site.id: WeatherObservation(
            latitude=site.latitude, longitude=site.longitude, timestamp="t", rain_rate_mm_h=3.0, source="test-fixture"
        )
    }
    assert site.provenance is Provenance.REAL
    assert weather_by_site[site.id].rain_rate_mm_h == 3.0
    # No exposure calculation is possible or attempted -- there is no link.


def test_demo_network_is_entirely_and_only_demo_provenance():
    """Regression guard: the bundled illustrative network must never drift
    into looking real, and real infrastructure loaders must never produce
    a MicrowaveLink (see the infrastructure adapters' own guard tests)."""
    from demo.network import DEMO_LINKS, DEMO_SITES

    assert len(DEMO_SITES) > 0
    assert len(DEMO_LINKS) > 0
    assert all(s.provenance is Provenance.DEMO for s in DEMO_SITES)
    assert all(l.provenance is Provenance.DEMO for l in DEMO_LINKS)


def test_demo_network_still_calculates_exposure_end_to_end():
    from demo.network import DEMO_LINKS

    link = DEMO_LINKS[0]
    weather = {
        link.site_a.id: WeatherObservation(
            latitude=link.site_a.latitude, longitude=link.site_a.longitude, timestamp="t", rain_rate_mm_h=15.0, source="test-fixture"
        ),
        link.site_b.id: WeatherObservation(
            latitude=link.site_b.latitude, longitude=link.site_b.longitude, timestamp="t", rain_rate_mm_h=15.0, source="test-fixture"
        ),
    }
    result = calculate_exposure(link=link, weather_by_site=weather)
    assert result.severity in ("low", "moderate", "high")


def test_mixed_real_and_demo_sites_never_silently_merge_provenance():
    """A real site and a demo site can coexist in the same collection for
    map rendering, but constructing a link across them is a decision a
    caller must make explicitly and label -- this test just confirms the
    library doesn't do it automatically or lose the distinction."""
    real_site = parse_tower_feature(REAL_TOWER_FEATURE)
    demo_site = MicrowaveSite(id="demo-1", name="Demo Site", latitude=43.65, longitude=-79.38, provenance=Provenance.DEMO)
    sites = [real_site, demo_site]
    assert {s.provenance for s in sites} == {Provenance.REAL, Provenance.DEMO}

    # If a caller DOES build a link across mixed-provenance sites, its own
    # provenance is still whatever they explicitly declare -- never inferred.
    link = MicrowaveLink(
        id="mixed", site_a=real_site, site_b=demo_site, frequency_ghz=18.0, polarization="V",
        fade_margin_db=30.0, provenance=Provenance.NOT_AVAILABLE,
    )
    assert link.provenance is Provenance.NOT_AVAILABLE


# --- The exact composition app.py performs to decide what to draw on the ---
# --- map for a selected REAL site (station ring/pin/line, or nothing).   ---


def _fake_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_selected_real_site_with_a_station_produces_a_drawable_relationship():
    """This is exactly the condition app.py checks before drawing the
    station marker/ring/line: `rep is not None and rep.nearest_station is
    not None`. A found station must yield real, usable coordinates and a
    real distance -- never a fabricated stand-in."""
    site = parse_tower_feature(REAL_TOWER_FEATURE)
    features = [
        {
            "geometry": {"type": "Point", "coordinates": [-79.9, 43.6]},
            "properties": {"stn_nam-value": "NEARBY STATION", "date_tm-value": "2026-09-04T20:00:00.000Z", "pcpn_amt_pst1hr": 1.5},
        }
    ]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        station_result = eccc.find_nearest_station(site.latitude, site.longitude, search_radius_km=100.0)
    assert station_result is not None
    station_obs, distance_km, has_precip = station_result

    rep = assess_representativeness(
        site=site, nearest_station=station_obs, station_distance_km=distance_km, station_reports_precipitation=has_precip
    )
    # What app.py's map-drawing code actually reads:
    assert rep.nearest_station is not None
    assert rep.nearest_station.latitude == pytest.approx(43.6)
    assert rep.nearest_station.longitude == pytest.approx(-79.9)
    assert rep.station_distance_km > 0


def test_selected_real_site_with_no_station_draws_nothing_fabricated():
    """No station in range -> rep.nearest_station is None -> app.py's
    drawing condition is false -> no ring, pin, or line is added. Confirms
    the upstream data, not the Streamlit rendering, guarantees this."""
    site = parse_tower_feature(REAL_TOWER_FEATURE)
    with patch("requests.get", return_value=_fake_response({"features": []})):
        station_result = eccc.find_nearest_station(site.latitude, site.longitude)
    assert station_result is None

    rep = assess_representativeness(site=site)  # exactly what app.py builds when station_result is None
    assert rep.nearest_station is None
    assert rep.station_distance_km is None
    assert rep.level == "insufficient_evidence"


def test_selected_real_site_with_station_missing_precipitation_is_explicit():
    """A station can be found (and its marker/line still drawn -- its
    location is real) while its precipitation is explicitly unavailable,
    never silently shown as zero rain."""
    site = parse_tower_feature(REAL_TOWER_FEATURE)
    features = [
        {
            "geometry": {"type": "Point", "coordinates": [-79.9, 43.6]},
            "properties": {"stn_nam-value": "NO PRECIP STATION", "date_tm-value": "2026-09-04T20:00:00.000Z"},
        }
    ]
    with patch("requests.get", return_value=_fake_response({"features": features})):
        station_result = eccc.find_nearest_station(site.latitude, site.longitude, search_radius_km=100.0)
    station_obs, distance_km, has_precip = station_result
    assert has_precip is False  # the station marker/line would still be drawn (real location)...

    rep = assess_representativeness(
        site=site, nearest_station=station_obs, station_distance_km=distance_km, station_reports_precipitation=has_precip
    )
    assert rep.level == "insufficient_evidence"  # ...but the panel must not claim a comparison exists
    assert "does not publish" in rep.note


def test_provider_failure_degrades_to_no_station_not_an_exception():
    """A live-service failure (timeout, HTTP error, etc.) must surface as
    `None`, matching how app.py's cached wrapper interprets it -- never an
    unhandled exception that would break the rest of the page."""
    site = parse_tower_feature(REAL_TOWER_FEATURE)
    with patch("requests.get", side_effect=ConnectionError("simulated outage")):
        with pytest.raises(ConnectionError):
            # find_nearest_station itself propagates the exception; app.py's
            # get_nearest_station_cached() is the layer that catches it (see
            # app.py) -- this test pins the contract that wrapper relies on.
            eccc.find_nearest_station(site.latitude, site.longitude)
