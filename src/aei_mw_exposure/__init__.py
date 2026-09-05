"""aei_mw_exposure: given weather observations and a terrestrial microwave
link, calculate the link's weather-related exposure using transparent,
published engineering methods (ITU-R P.838-3 / P.530).

This package has zero third-party runtime dependencies. Concrete weather
providers (e.g. Open-Meteo) live under ``aei_mw_exposure.providers`` and are
imported separately, so importing this package never pulls in networking
code.

Quick usage::

    from aei_mw_exposure import MicrowaveSite, MicrowaveLink, Provenance, WeatherObservation, calculate_exposure

    site_a = MicrowaveSite(id="a", name="Site A", latitude=43.65, longitude=-79.38, provenance=Provenance.DEMO)
    site_b = MicrowaveSite(id="b", name="Site B", latitude=43.78, longitude=-79.23, provenance=Provenance.DEMO)
    link = MicrowaveLink(id="l1", site_a=site_a, site_b=site_b, frequency_ghz=18.0,
                          polarization="V", fade_margin_db=32.0, provenance=Provenance.DEMO)

    weather = {
        "a": WeatherObservation(latitude=43.65, longitude=-79.38, timestamp="now",
                                 rain_rate_mm_h=12.0, source="test-fixture"),
        "b": WeatherObservation(latitude=43.78, longitude=-79.23, timestamp="now",
                                 rain_rate_mm_h=4.0, source="test-fixture"),
    }
    result = calculate_exposure(link=link, weather_by_site=weather)
    print(result.severity, result.exposure_ratio, result.attenuation.predicted_attenuation_db)
"""

from .exposure import (
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_MODERATE_THRESHOLD,
    ExposureSummary,
    LinkExposure,
    Severity,
    calculate_exposure,
    summarize,
)
from .geometry import haversine_km
from .microwave import MetadataValue, MicrowaveLink, MicrowaveSite, Polarization
from .provenance import Provenance
from .physics import (
    MAX_FREQ_GHZ,
    MIN_FREQ_GHZ,
    AttenuationEstimate,
    effective_path_length_km,
    estimate_rain_attenuation,
    rain_coefficients,
    specific_attenuation_db_km,
)
from .representativeness import (
    DEFAULT_DISAGREEMENT_THRESHOLD_MM_H,
    DEFAULT_MAX_STATION_DISTANCE_KM,
    RepresentativenessLevel,
    WeatherRepresentativeness,
    assess_representativeness,
)
from .weather import SOURCE_SYNTHETIC, SOURCE_TEST_FIXTURE, WeatherObservation, WeatherProvider, peak_rain

__version__ = "0.1.3"

__all__ = [
    "__version__",
    # microwave domain
    "MicrowaveSite",
    "MicrowaveLink",
    "Polarization",
    "Provenance",
    "MetadataValue",
    # weather domain
    "WeatherObservation",
    "WeatherProvider",
    "peak_rain",
    "SOURCE_SYNTHETIC",
    "SOURCE_TEST_FIXTURE",
    # geometry
    "haversine_km",
    # physics
    "AttenuationEstimate",
    "estimate_rain_attenuation",
    "specific_attenuation_db_km",
    "effective_path_length_km",
    "rain_coefficients",
    "MIN_FREQ_GHZ",
    "MAX_FREQ_GHZ",
    # exposure
    "LinkExposure",
    "ExposureSummary",
    "Severity",
    "calculate_exposure",
    "summarize",
    "DEFAULT_MODERATE_THRESHOLD",
    "DEFAULT_HIGH_THRESHOLD",
    # representativeness
    "WeatherRepresentativeness",
    "RepresentativenessLevel",
    "assess_representativeness",
    "DEFAULT_MAX_STATION_DISTANCE_KM",
    "DEFAULT_DISAGREEMENT_THRESHOLD_MM_H",
]
