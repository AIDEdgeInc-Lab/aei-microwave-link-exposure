import pytest

from aei_mw_exposure.physics import (
    MAX_FREQ_GHZ,
    MIN_FREQ_GHZ,
    effective_path_length_km,
    estimate_rain_attenuation,
    rain_coefficients,
    specific_attenuation_db_km,
)


def test_zero_rain_gives_zero_specific_attenuation():
    assert specific_attenuation_db_km(0.0, freq_ghz=18.0) == 0.0


def test_negative_rain_treated_as_zero():
    assert specific_attenuation_db_km(-5.0, freq_ghz=18.0) == 0.0


def test_specific_attenuation_increases_with_rain_rate():
    low = specific_attenuation_db_km(5.0, freq_ghz=18.0)
    high = specific_attenuation_db_km(50.0, freq_ghz=18.0)
    assert high > low


def test_specific_attenuation_increases_with_frequency_in_typical_band():
    # Monotonic increase with frequency holds across common backhaul bands
    # (well below the table's high-frequency saturation region).
    lower = specific_attenuation_db_km(20.0, freq_ghz=6.0)
    higher = specific_attenuation_db_km(20.0, freq_ghz=38.0)
    assert higher > lower


def test_polarization_changes_result():
    h = specific_attenuation_db_km(20.0, freq_ghz=18.0, polarization="H")
    v = specific_attenuation_db_km(20.0, freq_ghz=18.0, polarization="V")
    assert h != v


def test_rain_coefficients_out_of_range_raises():
    with pytest.raises(ValueError):
        rain_coefficients(freq_ghz=MAX_FREQ_GHZ + 1)
    with pytest.raises(ValueError):
        rain_coefficients(freq_ghz=MIN_FREQ_GHZ - 1)


def test_effective_path_length_is_shorter_than_geometric_for_positive_rain():
    d_eff = effective_path_length_km(path_length_km=20.0, rain_rate_mm_h=30.0)
    assert 0.0 < d_eff < 20.0


def test_effective_path_length_zero_for_zero_length():
    assert effective_path_length_km(path_length_km=0.0, rain_rate_mm_h=30.0) == 0.0


def test_estimate_is_deterministic():
    a = estimate_rain_attenuation(path_length_km=10.0, rain_rate_mm_h=20.0, freq_ghz=18.0, polarization="V")
    b = estimate_rain_attenuation(path_length_km=10.0, rain_rate_mm_h=20.0, freq_ghz=18.0, polarization="V")
    assert a == b


def test_estimate_zero_rain_gives_zero_attenuation():
    est = estimate_rain_attenuation(path_length_km=10.0, rain_rate_mm_h=0.0, freq_ghz=18.0, polarization="V")
    assert est.predicted_attenuation_db == 0.0
    assert est.k == 0.0
    assert est.alpha == 0.0


def test_estimate_exposes_full_calculation_chain():
    est = estimate_rain_attenuation(path_length_km=10.0, rain_rate_mm_h=20.0, freq_ghz=18.0, polarization="V")
    assert est.k > 0
    assert est.alpha > 0
    assert est.specific_attenuation_db_km > 0
    assert est.effective_path_length_km > 0
    assert est.predicted_attenuation_db == pytest.approx(
        est.specific_attenuation_db_km * est.effective_path_length_km, rel=1e-2
    )
    assert "ITU-R" in est.method
    assert len(est.assumption) > 20  # non-empty, human-readable explanation


def test_estimate_rejects_negative_inputs():
    with pytest.raises(ValueError):
        estimate_rain_attenuation(path_length_km=-1.0, rain_rate_mm_h=10.0, freq_ghz=18.0)
    with pytest.raises(ValueError):
        estimate_rain_attenuation(path_length_km=10.0, rain_rate_mm_h=-1.0, freq_ghz=18.0)
