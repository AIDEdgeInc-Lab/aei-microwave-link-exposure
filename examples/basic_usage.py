"""Minimal runnable example: calculate one link's exposure with no network
access, no Streamlit, and no demo network -- just the public API.

Run: python examples/basic_usage.py
"""

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance, WeatherObservation, calculate_exposure

# provenance is required and explicit: these are made-up points for this example,
# so they're honestly labeled DEMO, not asserted as real infrastructure.
site_a = MicrowaveSite(id="a", name="Toronto North", latitude=43.8, longitude=-79.4, provenance=Provenance.DEMO)
site_b = MicrowaveSite(id="b", name="Toronto East", latitude=43.7, longitude=-79.2, provenance=Provenance.DEMO)

link = MicrowaveLink(
    id="L1",
    site_a=site_a,
    site_b=site_b,
    frequency_ghz=18.0,
    polarization="V",
    fade_margin_db=32.0,
    provenance=Provenance.DEMO,
    # length_km is not supplied -- it's derived from the two sites' real coordinates
)
print(f"Link length (haversine): {link.length_km:.2f} km")

# Stand-in for a real weather fetch -- any WeatherProvider works the same way.
weather_by_site = {
    site_a.id: WeatherObservation(
        latitude=site_a.latitude, longitude=site_a.longitude,
        timestamp="2026-09-04T14:00", rain_rate_mm_h=22.0, source="example-fixture",
    ),
    site_b.id: WeatherObservation(
        latitude=site_b.latitude, longitude=site_b.longitude,
        timestamp="2026-09-04T14:00", rain_rate_mm_h=6.0, source="example-fixture",
    ),
}

result = calculate_exposure(link=link, weather_by_site=weather_by_site)

print("\n--- OBSERVED ---")
print(f"Rain rate used: {result.rain_rate_mm_h:.1f} mm/h (from site {result.source_site_id!r})")
print(result.rain_rate_assumption)

print("\n--- CALCULATED ---")
a = result.attenuation
print(f"Method: {a.method}")
print(f"k={a.k}, alpha={a.alpha}  ->  specific attenuation {a.specific_attenuation_db_km} dB/km")
print(f"Effective path length: {a.effective_path_length_km} km (geometric: {a.path_length_km:.2f} km)")
print(f"Predicted attenuation: {a.predicted_attenuation_db} dB")
print(f"Exposure ratio: {result.exposure_ratio:.2%} of the {link.fade_margin_db:.0f} dB fade margin")

print(f"\n--- INFERRED ---\nSeverity: {result.severity.upper()}")
print(result.operational_note)
