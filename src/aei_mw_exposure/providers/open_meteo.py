"""Open-Meteo weather provider: free, keyless, public.

This is one implementation of ``aei_mw_exposure.weather.WeatherProvider`` --
not a privileged one. A CSV-backed provider, a test-fixture provider, or
eventually an operator feed would look exactly the same to the exposure
calculation: an object that hands back ``WeatherObservation``.

Requires ``requests``, installed via the ``open-meteo`` extra
(``pip install aei-microwave-link-exposure[open-meteo]``); the core package does
not depend on it.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from ..microwave import MicrowaveSite
from ..weather import WeatherObservation

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"


class OpenMeteoProvider:
    """Implements ``WeatherProvider`` against api.open-meteo.com."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def get_current(self, site: MicrowaveSite) -> WeatherObservation:
        data = self._fetch(site)
        current = _section(data, "current")
        rain, precipitation = current.get("rain"), current.get("precipitation")
        value = rain if rain else precipitation   # same preference as before: rain, then precipitation when rain is 0 or missing
        if value is None:
            value = rain
        if value is None:
            raise ProviderResponseError(
                f"Open-Meteo returned neither rain nor precipitation for site {site.id!r}; no rain rate was substituted.")
        return WeatherObservation(
            latitude=site.latitude,
            longitude=site.longitude,
            timestamp=_required(current, "time", "current"),
            rain_rate_mm_h=_number(value, "current rain/precipitation"),
            source=SOURCE,
            temperature_c=_optional_float(current.get("temperature_2m")),
            wind_speed_kmh=_optional_float(current.get("wind_speed_10m")),
            fetched_at=time.time(),
            site_id=site.id,
        )

    def get_forecast(self, site: MicrowaveSite, hours: int = 24) -> List[WeatherObservation]:
        """Next ``hours`` hourly observations from "now" (precipitation only)."""
        data = self._fetch(site)
        now = _required(_section(data, "current"), "time", "current")
        hourly = _section(data, "hourly")
        hourly_times = _required(hourly, "time", "hourly")
        hourly_precip = _required(hourly, "precipitation", "hourly")
        if not isinstance(hourly_times, list) or not isinstance(hourly_precip, list) or len(hourly_times) != len(hourly_precip):
            raise ProviderResponseError("Open-Meteo returned hourly time and precipitation series that do not line up; nothing was read.")

        start_idx = next((i for i, t in enumerate(hourly_times) if t >= now), 0)
        fetched_at = time.time()
        observations = []
        for t, precip in zip(hourly_times[start_idx : start_idx + hours], hourly_precip[start_idx : start_idx + hours]):
            if precip is None:
                raise ProviderResponseError(
                    f"Open-Meteo returned no precipitation for {t} at site {site.id!r}; a missing hour is not read as 0 mm/h.")
            observations.append(
                WeatherObservation(
                    latitude=site.latitude,
                    longitude=site.longitude,
                    timestamp=t,
                    rain_rate_mm_h=_number(precip, f"hourly precipitation at {t}"),
                    source=SOURCE,
                    fetched_at=fetched_at,
                    site_id=site.id,
                )
            )
        return observations

    def get_current_many(self, sites: Iterable[MicrowaveSite]) -> Dict[str, WeatherObservation]:
        """Convenience batch fetch: one request per site, in order."""
        return {s.id: self.get_current(s) for s in sites}

    def _fetch(self, site: MicrowaveSite) -> Dict[str, Any]:
        params = {
            "latitude": site.latitude,
            "longitude": site.longitude,
            "current": "precipitation,rain,temperature_2m,wind_speed_10m",
            "hourly": "precipitation",
            "forecast_days": 2,
            "timezone": "auto",
        }
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ProviderResponseError("Open-Meteo returned a response that is not a JSON object; nothing was read.")
        return data


class ProviderResponseError(ValueError):
    """The weather service answered, but not with data this provider can use as it is (a missing section or field, a missing
    rain value, a non-numeric or non-finite number). Nothing is substituted. Subclasses ValueError."""


def _section(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ProviderResponseError(f"Open-Meteo response has no '{key}' section; nothing was read.")
    return value


def _required(section: Dict[str, Any], key: str, where: str) -> Any:
    if section.get(key) is None:
        raise ProviderResponseError(f"Open-Meteo response has no '{where}.{key}' value; nothing was read.")
    return section[key]


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProviderResponseError(f"Open-Meteo returned a non-numeric or non-finite {what}: {value!r}")
    return float(value)


def _optional_float(value: Any) -> Optional[float]:
    return None if value is None else _number(value, "value")
