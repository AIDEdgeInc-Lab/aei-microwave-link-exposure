import pytest

from aei_mw_exposure import (
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_MODERATE_THRESHOLD,
    MicrowaveLink,
    MicrowaveSite,
    Provenance,
    WeatherObservation,
    calculate_exposure,
    summarize,
)


def make_link(fade_margin_db: float = 30.0, freq_ghz: float = 18.0, length_scale: float = 1.0):
    a = MicrowaveSite(id="a", name="Site A", latitude=43.65, longitude=-79.38, provenance=Provenance.DEMO)
    # ~10km east, scaled by length_scale for longer/shorter test links
    b = MicrowaveSite(id="b", name="Site B", latitude=43.65, longitude=-79.38 + 0.13 * length_scale, provenance=Provenance.DEMO)
    return MicrowaveLink(
        id="l1", site_a=a, site_b=b, frequency_ghz=freq_ghz, polarization="V", fade_margin_db=fade_margin_db, provenance=Provenance.DEMO
    )


def weather_for(link, rain_a: float, rain_b: float):
    return {
        link.site_a.id: WeatherObservation(
            latitude=link.site_a.latitude, longitude=link.site_a.longitude, timestamp="t", rain_rate_mm_h=rain_a, source="test-fixture"
        ),
        link.site_b.id: WeatherObservation(
            latitude=link.site_b.latitude, longitude=link.site_b.longitude, timestamp="t", rain_rate_mm_h=rain_b, source="test-fixture"
        ),
    }


def test_zero_rain_is_low_severity():
    link = make_link()
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 0.0, 0.0))
    assert result.severity == "low"
    assert result.exposure_ratio == 0.0
    assert result.attenuation.predicted_attenuation_db == 0.0


def test_heavy_rain_on_a_long_high_frequency_link_reaches_high_severity():
    link = make_link(fade_margin_db=15.0, freq_ghz=23.0, length_scale=3.0)
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 80.0, 80.0))
    assert result.severity == "high"
    assert result.exposure_ratio >= DEFAULT_HIGH_THRESHOLD


def test_moderate_rain_can_land_in_moderate_band():
    # Chosen so predicted attenuation sits between the two thresholds for
    # this specific link -- not asserting a universal rain-rate boundary.
    link = make_link(fade_margin_db=20.0, freq_ghz=18.0, length_scale=2.0)
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 15.0, 15.0))
    assert DEFAULT_MODERATE_THRESHOLD <= result.exposure_ratio < DEFAULT_HIGH_THRESHOLD
    assert result.severity == "moderate"


def test_fade_margin_changes_severity_for_identical_weather_and_geometry():
    generous = make_link(fade_margin_db=60.0)
    tight = make_link(fade_margin_db=5.0)
    weather = weather_for(generous, 40.0, 40.0)  # same coordinates as `tight`'s link
    generous_result = calculate_exposure(link=generous, weather_by_site=weather)
    tight_result = calculate_exposure(link=tight, weather_by_site=weather_for(tight, 40.0, 40.0))
    assert generous_result.attenuation.predicted_attenuation_db == pytest.approx(
        tight_result.attenuation.predicted_attenuation_db
    )
    assert generous_result.exposure_ratio < tight_result.exposure_ratio
    assert generous_result.severity in ("low", "moderate")
    assert tight_result.severity == "high"


def test_exposure_ratio_is_attenuation_over_fade_margin():
    link = make_link(fade_margin_db=25.0)
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 30.0, 30.0))
    expected_ratio = round(result.attenuation.predicted_attenuation_db / link.fade_margin_db, 3)
    assert result.exposure_ratio == expected_ratio


def test_worse_endpoint_is_selected_deterministically():
    link = make_link()
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 5.0, 40.0))
    assert result.source_site_id == link.site_b.id
    assert result.rain_rate_mm_h == 40.0
    assert "conservative stand-in" in result.rain_rate_assumption

    result2 = calculate_exposure(link=link, weather_by_site=weather_for(link, 40.0, 5.0))
    assert result2.source_site_id == link.site_a.id
    assert result2.rain_rate_mm_h == 40.0


def test_tie_between_endpoints_picks_site_a():
    link = make_link()
    result = calculate_exposure(link=link, weather_by_site=weather_for(link, 20.0, 20.0))
    assert result.source_site_id == link.site_a.id


def test_missing_endpoint_weather_raises_with_clear_message():
    link = make_link()
    incomplete = {link.site_a.id: WeatherObservation(latitude=0, longitude=0, timestamp="t", rain_rate_mm_h=1.0, source="test-fixture")}
    with pytest.raises(ValueError, match=link.site_b.id):
        calculate_exposure(link=link, weather_by_site=incomplete)


def test_missing_optional_weather_fields_do_not_break_calculation():
    link = make_link()
    weather = weather_for(link, 10.0, 10.0)
    # rain_rate_mm_h is set; temperature/wind/site_id left at their defaults (None)
    assert weather[link.site_a.id].temperature_c is None
    result = calculate_exposure(link=link, weather_by_site=weather)
    assert result.severity in ("low", "moderate", "high")


def test_custom_thresholds_change_bucketing():
    link = make_link(fade_margin_db=20.0)
    weather = weather_for(link, 10.0, 10.0)
    default_result = calculate_exposure(link=link, weather_by_site=weather)
    strict_result = calculate_exposure(link=link, weather_by_site=weather, moderate_threshold=0.01, high_threshold=0.05)
    assert strict_result.severity == "high"
    assert default_result.exposure_ratio == strict_result.exposure_ratio  # same math, different bucketing


def test_summarize_counts_by_severity():
    low_link = make_link(fade_margin_db=60.0)
    high_link = MicrowaveLink(
        id="l2",
        site_a=MicrowaveSite(id="c", name="C", latitude=43.9, longitude=-79.9, provenance=Provenance.DEMO),
        site_b=MicrowaveSite(id="d", name="D", latitude=44.1, longitude=-80.1, provenance=Provenance.DEMO),
        frequency_ghz=23.0,
        polarization="V",
        fade_margin_db=5.0,
        provenance=Provenance.DEMO,
    )
    exposures = [
        calculate_exposure(link=low_link, weather_by_site=weather_for(low_link, 5.0, 5.0)),
        calculate_exposure(
            link=high_link,
            weather_by_site={
                "c": WeatherObservation(latitude=43.9, longitude=-79.9, timestamp="t", rain_rate_mm_h=90.0, source="test-fixture"),
                "d": WeatherObservation(latitude=44.1, longitude=-80.1, timestamp="t", rain_rate_mm_h=90.0, source="test-fixture"),
            },
        ),
    ]
    summary = summarize(exposures)
    assert summary.total_links == 2
    assert summary.exposed_high == 1
    assert summary.exposed_moderate_plus == 1
    assert "precipitation" in summary.driver
