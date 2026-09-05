"""The library's single entry point: weather + a link -> exposure.

Three explicitly separated layers, kept distinct on purpose:

  OBSERVED    -- what the weather provider reported, unmodified
                 (LinkExposure.rain_rate_mm_h / .source_site_id).
  CALCULATED  -- what ITU-R P.838-3 / P.530 physics implies for this hop,
                 given that rain rate (LinkExposure.attenuation). A
                 defensible estimate, not a measurement.
  INFERRED    -- a hedged, plain-language statement about what that would
                 *typically* mean for link capacity, given the link's own
                 fade margin (LinkExposure.operational_note). Never an
                 outage claim -- this library has no outage data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from .microwave import MicrowaveLink
from .physics import AttenuationEstimate, estimate_rain_attenuation
from .weather import WeatherObservation

Severity = Literal["low", "moderate", "high"]

# exposure_ratio = predicted attenuation / fade margin. A stated, simple
# convention for bucketing this library's output -- not a validated risk
# model, and callers needing different bands can pass their own thresholds.
DEFAULT_MODERATE_THRESHOLD = 0.3
DEFAULT_HIGH_THRESHOLD = 0.7


def _severity(ratio: float, moderate_threshold: float, high_threshold: float) -> Severity:
    if ratio >= high_threshold:
        return "high"
    if ratio >= moderate_threshold:
        return "moderate"
    return "low"


@dataclass(frozen=True)
class LinkExposure:
    """The full, inspectable result of one exposure calculation."""

    link: MicrowaveLink
    rain_rate_mm_h: float
    source_site_id: str
    rain_rate_assumption: str
    attenuation: AttenuationEstimate
    exposure_ratio: float
    severity: Severity
    operational_note: str


def calculate_exposure(
    link: MicrowaveLink,
    weather_by_site: Mapping[str, WeatherObservation],
    moderate_threshold: float = DEFAULT_MODERATE_THRESHOLD,
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
) -> LinkExposure:
    """Calculate one link's weather-related exposure.

    ``weather_by_site`` must contain an entry for both ``link.site_a.id``
    and ``link.site_b.id`` -- raises ``ValueError`` naming whichever is
    missing, rather than a bare ``KeyError``.

    The rain rate used is the HIGHER of the two endpoints' observed rain
    rate: a conservative stand-in for the (unobserved) rain rate along the
    path, not a measurement of it. That assumption is preserved on the
    result, not just in this docstring -- see ``rain_rate_assumption``.
    """
    for site_id in (link.site_a.id, link.site_b.id):
        if site_id not in weather_by_site:
            raise ValueError(f"no weather observation provided for site {site_id!r}")

    obs_a = weather_by_site[link.site_a.id]
    obs_b = weather_by_site[link.site_b.id]

    if obs_a.rain_rate_mm_h >= obs_b.rain_rate_mm_h:
        rain_used, source_site_id = obs_a.rain_rate_mm_h, link.site_a.id
    else:
        rain_used, source_site_id = obs_b.rain_rate_mm_h, link.site_b.id

    assumption = (
        f"Using the higher of the two endpoints' observed rain rate "
        f"({source_site_id}: {rain_used:.1f} mm/h) as a conservative stand-in "
        f"for the rain rate along the path -- the actual path rain rate is not "
        f"observed by either endpoint."
    )

    estimate = estimate_rain_attenuation(
        path_length_km=link.length_km,
        rain_rate_mm_h=rain_used,
        freq_ghz=link.frequency_ghz,
        polarization=link.polarization,
    )

    ratio = round(estimate.predicted_attenuation_db / link.fade_margin_db, 3)
    severity = _severity(ratio, moderate_threshold, high_threshold)

    if severity == "high":
        note = (
            f"Predicted attenuation ({estimate.predicted_attenuation_db:.1f} dB) is at or "
            f"above {int(high_threshold * 100)}% of this link's stated fade margin "
            f"({link.fade_margin_db:.0f} dB). A link this exposed would typically be "
            f"expected to step down modulation (reduced capacity) or approach its fade "
            f"floor -- this is not an outage claim; no outage data was used to produce it."
        )
    elif severity == "moderate":
        note = (
            f"Predicted attenuation ({estimate.predicted_attenuation_db:.1f} dB) is a "
            f"moderate fraction of the fade margin ({link.fade_margin_db:.0f} dB) -- "
            f"worth watching, not yet a likely capacity impact."
        )
    else:
        note = (
            f"Predicted attenuation ({estimate.predicted_attenuation_db:.1f} dB) is small "
            f"relative to the fade margin ({link.fade_margin_db:.0f} dB); no meaningful "
            f"exposure implied by this calculation."
        )

    return LinkExposure(
        link=link,
        rain_rate_mm_h=rain_used,
        source_site_id=source_site_id,
        rain_rate_assumption=assumption,
        attenuation=estimate,
        exposure_ratio=ratio,
        severity=severity,
        operational_note=note,
    )


@dataclass(frozen=True)
class ExposureSummary:
    total_links: int
    exposed_moderate_plus: int
    exposed_high: int
    driver: str


def summarize(exposures: list[LinkExposure]) -> ExposureSummary:
    """Aggregate counts. Only reports what the calculation actually supports:
    counts by severity and the one driver this library models (precipitation).
    """
    moderate_plus = sum(1 for e in exposures if e.severity in ("moderate", "high"))
    high = sum(1 for e in exposures if e.severity == "high")
    return ExposureSummary(
        total_links=len(exposures),
        exposed_moderate_plus=moderate_plus,
        exposed_high=high,
        driver="precipitation (rain attenuation, ITU-R P.838-3)",
    )
