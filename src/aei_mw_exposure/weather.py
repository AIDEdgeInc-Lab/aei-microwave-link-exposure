"""Normalized weather domain type + the adapter interface.

The calculation layer (physics/exposure) only ever sees ``WeatherObservation``.
It has no idea whether that observation came from Open-Meteo, a CSV, a unit
test fixture, or eventually an operator feed -- that's the point of the
``WeatherProvider`` interface below: one small, swappable seam, not a
plugin framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, runtime_checkable

# Conventional values for WeatherObservation.source. Not enforced -- a
# free-text field kept honest by convention, because inventing an enum for
# every future provider is exactly the kind of framework this library
# avoids. "live" data must never be silently mixed with "synthetic" data
# under the same source label.
SOURCE_SYNTHETIC = "synthetic"
SOURCE_TEST_FIXTURE = "test-fixture"


@dataclass(frozen=True)
class WeatherObservation:
    """A single normalized weather observation at a point in time.

    Represents either a current reading or one forecast time-step -- not an
    aggregate. If a caller wants "the worst of the next 24 hours", they
    fetch 24 of these and reduce them (see ``peak_rain`` below); this type
    itself never blends multiple time points.
    """

    latitude: float
    longitude: float
    timestamp: str  # provider-native or ISO 8601; kept as a plain string deliberately
    rain_rate_mm_h: float
    source: str
    temperature_c: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    fetched_at: Optional[float] = None  # unix time the fetch happened, for freshness checks
    site_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.rain_rate_mm_h < 0:
            raise ValueError(f"rain_rate_mm_h cannot be negative: {self.rain_rate_mm_h}")


@runtime_checkable
class WeatherProvider(Protocol):
    """The one adapter seam. Implement this against any weather source.

    Only ``get_current`` is required. A provider that can also forecast
    may add ``get_forecast(site, hours) -> list[WeatherObservation]``, but
    that's a convention, not part of this Protocol -- callers that need a
    forecast should check for the method or use a provider-specific type.
    """

    def get_current(self, site) -> WeatherObservation: ...  # noqa: ANN001


def peak_rain(observations: Iterable[WeatherObservation]) -> WeatherObservation:
    """The observation with the highest rain rate in a sequence.

    Generic reduction used to turn "a short forecast window" into a single
    worst-case ``WeatherObservation`` the exposure calculation can consume.
    Raises ``ValueError`` on an empty sequence rather than returning None.
    """
    observations = list(observations)
    if not observations:
        raise ValueError("peak_rain() requires at least one observation")
    return max(observations, key=lambda o: o.rain_rate_mm_h)
