"""How representative is the weather evidence available for a site?

A weather value reported for a city (or a coarse model grid cell) may not
match conditions at a specific infrastructure site several kilometres
away, especially during spatially variable precipitation. This module
answers exactly one question: given whatever weather evidence is actually
available near a site, how much of it agrees, and how far away is it?

WHAT THIS IS
------------
A transparent comparison of independently-sourced weather evidence near a
point: a nearby observing station (if one exists), a weather-model value
at the site's own coordinates, and (optionally) a radar-estimated rate at
the site's own coordinates. The distance and any disagreement between
sources are calculated facts. The final "level" is a simple, stated,
overridable convention -- not a statistical confidence score.

WHAT THIS IS NOT
-----------------
- Not hyperlocal forecasting or microclimate prediction. Nothing here
  predicts anything; it compares evidence that already exists right now.
- Not a numeric confidence percentage. There is no validated statistical
  methodology behind "73% confidence" and this module does not invent one.
- Not a claim that a station or model value is "correct." Both can be
  right for their own location and still disagree with conditions at the
  site in question -- that disagreement is the finding, not an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .microwave import MicrowaveSite
from .weather import WeatherObservation

RepresentativenessLevel = Literal[
    "insufficient_evidence", "consistent", "moderate_disagreement", "high_disagreement"
]

# Simple, named, overridable conventions -- not a validated meteorological
# standard. Kept in the same spirit as DEFAULT_MODERATE_THRESHOLD /
# DEFAULT_HIGH_THRESHOLD in exposure.py: stated plainly, easy to override,
# never presented as more rigorous than they are.
DEFAULT_MAX_STATION_DISTANCE_KM = 50.0
"""Beyond this distance, a station's reading is treated as too far from
the site to speak to conditions there on its own."""

DEFAULT_DISAGREEMENT_THRESHOLD_MM_H = 2.0
"""Difference between two independent precipitation readings, in mm/h,
above which this module calls it a meaningful disagreement rather than
noise/rounding."""


@dataclass(frozen=True)
class WeatherRepresentativeness:
    """The full, inspectable comparison for one site.

    OBSERVED: ``nearest_station`` and ``model_observation`` (and
    ``radar_observation`` if provided) -- each a plain ``WeatherObservation``
    from its own source, unmodified.
    CALCULATED: ``station_distance_km`` and ``precipitation_difference_mm_h``.
    INFERRED: ``level`` and ``note`` -- see module docstring for what that
    is and is not.
    """

    site: MicrowaveSite
    nearest_station: Optional[WeatherObservation]
    station_distance_km: Optional[float]
    station_reports_precipitation: Optional[bool]
    """None when there is no station at all. When ``nearest_station`` is
    set, this is the authoritative signal for whether its
    ``rain_rate_mm_h`` is a real reading -- that field is a required float
    everywhere in this library and cannot itself represent "unknown", so a
    station that simply doesn't publish precipitation still has
    ``rain_rate_mm_h == 0.0`` as a technical placeholder. Never read that
    field without checking this one first."""
    model_observation: Optional[WeatherObservation]
    radar_observation: Optional[WeatherObservation]
    precipitation_difference_mm_h: Optional[float]
    level: RepresentativenessLevel
    note: str


def assess_representativeness(
    site: MicrowaveSite,
    nearest_station: Optional[WeatherObservation] = None,
    station_distance_km: Optional[float] = None,
    station_reports_precipitation: bool = True,
    model_observation: Optional[WeatherObservation] = None,
    radar_observation: Optional[WeatherObservation] = None,
    max_station_distance_km: float = DEFAULT_MAX_STATION_DISTANCE_KM,
    disagreement_threshold_mm_h: float = DEFAULT_DISAGREEMENT_THRESHOLD_MM_H,
) -> WeatherRepresentativeness:
    """Compare whatever weather evidence is actually available for ``site``.

    Every input is optional except ``site`` -- a real deployment may not
    have a nearby station, may not have a model reading, may not have
    radar coverage. Missing evidence is handled explicitly, never
    invented: with less evidence, the result is a lower-confidence
    ``level``, not a fabricated value.

    If ``nearest_station`` is given, ``station_distance_km`` must be given
    too (the distance is computed by the caller -- see
    ``providers/eccc.py`` -- because it depends on the caller's own
    geometry choices, e.g. which two coordinates were compared).

    ``station_reports_precipitation`` must be set to False by the caller
    when the nearest station exists but does not publish a precipitation
    field -- ``WeatherObservation.rain_rate_mm_h`` cannot itself represent
    "unknown" (it's a required float everywhere else in this library), so
    this flag is the authoritative signal, not the field's value.
    """
    if nearest_station is not None and station_distance_km is None:
        raise ValueError("station_distance_km is required when nearest_station is given")

    # None (not just False) when there's no station at all -- "no station"
    # and "station exists but is silent on precipitation" are different
    # facts and both need to survive on the result, not just inside this
    # function's local reasoning.
    reports_precipitation = station_reports_precipitation if nearest_station is not None else None

    diff: Optional[float] = None
    if nearest_station is not None and model_observation is not None and reports_precipitation:
        diff = round(abs(nearest_station.rain_rate_mm_h - model_observation.rain_rate_mm_h), 2)

    level, note = _classify(
        station_distance_km=station_distance_km,
        difference_mm_h=diff,
        has_model=model_observation is not None,
        station_reports_precipitation=reports_precipitation,
        max_station_distance_km=max_station_distance_km,
        disagreement_threshold_mm_h=disagreement_threshold_mm_h,
    )

    return WeatherRepresentativeness(
        site=site,
        nearest_station=nearest_station,
        station_distance_km=station_distance_km,
        station_reports_precipitation=reports_precipitation,
        model_observation=model_observation,
        radar_observation=radar_observation,
        precipitation_difference_mm_h=diff,
        level=level,
        note=note,
    )


def _classify(
    station_distance_km: Optional[float],
    difference_mm_h: Optional[float],
    has_model: bool,
    station_reports_precipitation: Optional[bool],
    max_station_distance_km: float,
    disagreement_threshold_mm_h: float,
) -> tuple[RepresentativenessLevel, str]:
    if station_distance_km is None:
        return (
            "insufficient_evidence",
            "No observing station was found near this site within the search radius used. "
            "There is no independent evidence to compare against the model value.",
        )

    far = station_distance_km > max_station_distance_km
    if difference_mm_h is None:
        if station_reports_precipitation is False:
            reason = "it does not publish a precipitation reading"
        elif not has_model:
            reason = "no model value was available to compare against it"
        else:
            reason = "a comparison value was missing"
        far_clause = (
            f" (also beyond the {max_station_distance_km:.0f} km convention used here)" if far else ""
        )
        return (
            "insufficient_evidence",
            f"The nearest station is {station_distance_km:.1f} km away{far_clause}, but {reason}, "
            f"so no disagreement could be calculated.",
        )

    disagree = difference_mm_h > disagreement_threshold_mm_h
    if far and disagree:
        return (
            "high_disagreement",
            f"The nearest station is {station_distance_km:.1f} km away (beyond the "
            f"{max_station_distance_km:.0f} km convention) AND the station/model precipitation "
            f"values differ by {difference_mm_h:.1f} mm/h (beyond the {disagreement_threshold_mm_h:.1f} "
            f"mm/h convention). Treat the weather value at this site as weakly supported.",
        )
    if far or disagree:
        return (
            "moderate_disagreement",
            (
                f"The nearest station is {station_distance_km:.1f} km away, beyond the "
                f"{max_station_distance_km:.0f} km convention used here. "
                if far
                else f"Station and model precipitation differ by {difference_mm_h:.1f} mm/h, "
                f"above the {disagreement_threshold_mm_h:.1f} mm/h convention used here. "
            )
            + "Available weather sources show meaningful spatial disagreement at this location.",
        )
    return (
        "consistent",
        f"The nearest station is {station_distance_km:.1f} km away and its precipitation reading "
        f"is within {disagreement_threshold_mm_h:.1f} mm/h of the model value at this site's "
        f"coordinates. Available evidence does not show meaningful disagreement.",
    )
