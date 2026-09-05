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
        current = data["current"]
        return WeatherObservation(
            latitude=site.latitude,
            longitude=site.longitude,
            timestamp=current["time"],
            rain_rate_mm_h=float(current.get("rain") or current.get("precipitation") or 0.0),
            source=SOURCE,
            temperature_c=_optional_float(current.get("temperature_2m")),
            wind_speed_kmh=_optional_float(current.get("wind_speed_10m")),
            fetched_at=time.time(),
            site_id=site.id,
        )

    def get_forecast(self, site: MicrowaveSite, hours: int = 24) -> List[WeatherObservation]:
        """Next ``hours`` hourly observations from "now" (precipitation only)."""
        data = self._fetch(site)
        now = data["current"]["time"]
        hourly_times = data["hourly"]["time"]
        hourly_precip = data["hourly"]["precipitation"]

        start_idx = next((i for i, t in enumerate(hourly_times) if t >= now), 0)
        fetched_at = time.time()
        observations = []
        for t, precip in zip(hourly_times[start_idx : start_idx + hours], hourly_precip[start_idx : start_idx + hours]):
            observations.append(
                WeatherObservation(
                    latitude=site.latitude,
                    longitude=site.longitude,
                    timestamp=t,
                    rain_rate_mm_h=float(precip or 0.0),
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
        return resp.json()


def _optional_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)
