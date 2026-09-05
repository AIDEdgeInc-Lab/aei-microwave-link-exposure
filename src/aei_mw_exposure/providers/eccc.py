"""Environment and Climate Change Canada (ECCC) / MSC GeoMet: real
observing-station readings and radar-estimated precipitation.

Two live, official, public services (both verified live during this
project's research, not assumed from documentation):

- **SWOB-Realtime** (Surface Weather Observations, last 30 days), OGC API -
  Features: https://api.weather.gc.ca/collections/swob-realtime
  One row per station per observation. Includes real station name,
  coordinates, timestamp, and (when the station reports it)
  ``pcpn_amt_pst1hr`` -- precipitation accumulated in the past hour, mm.
  Not every station reports precipitation; this module returns ``None``
  rather than guessing when it doesn't.

- **Radar mosaic** (``RADAR_1KM_RRAI``, "Radar precipitation rate for
  rain [mm/h]"), WMS ``GetFeatureInfo``:
  https://geo.weather.gc.ca/geomet -- a genuine point query against a
  1 km-resolution North American radar composite, updated every 6
  minutes. This is a **remote-sensing estimate** derived from reflectivity
  (a Z-R relationship), not a direct gauge measurement -- labelled as such
  everywhere it's used.

Both sources are used here to build ordinary ``WeatherObservation``
objects -- no new domain type was needed for "a station's own reading" or
"a radar cell's own reading." What's new (see ``representativeness.py``)
is comparing them.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..microwave import MicrowaveSite
from ..weather import WeatherObservation

SWOB_REALTIME_URL = "https://api.weather.gc.ca/collections/swob-realtime/items"
RADAR_WMS_URL = "https://geo.weather.gc.ca/geomet"
RADAR_LAYER = "RADAR_1KM_RRAI"

SOURCE_STATION = "ECCC SWOB-Realtime"
SOURCE_RADAR = "ECCC Radar (RADAR_1KM_RRAI, radar-estimated, not gauge-measured)"

_KM_PER_DEGREE_LAT = 111.32  # approximation, fine at this scale -- see find_nearest_station


def find_nearest_station(
    latitude: float,
    longitude: float,
    search_radius_km: float = 50.0,
    window_minutes: int = 90,
    timeout: float = 15.0,
) -> Optional[Tuple[WeatherObservation, float, bool]]:
    """The closest reporting station to (latitude, longitude) within
    ``search_radius_km``, using observations from the last
    ``window_minutes``. Returns ``(observation, distance_km,
    reports_precipitation)``, or ``None`` if no station reported in that
    window/radius at all.

    ``reports_precipitation`` is False when the nearest station exists
    (name, distance, and timestamp are real) but does not publish a
    precipitation field -- a real, common case (confirmed against live
    data), not an error. Callers must check this before comparing
    ``observation.rain_rate_mm_h`` against anything.

    Queries a bounding box (not a true radius) sized from
    ``search_radius_km``, then computes exact haversine distance to every
    station returned and keeps the nearest -- the bbox is just a coarse
    pre-filter, not the actual selection criterion.
    """
    import requests

    from ..geometry import haversine_km

    deg = search_radius_km / _KM_PER_DEGREE_LAT
    bbox = f"{longitude - deg},{latitude - deg},{longitude + deg},{latitude + deg}"

    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "bbox": bbox,
        "datetime": f"{start}/{end}",
        "limit": 300,
        "f": "json",
    }
    resp = requests.get(SWOB_REALTIME_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    latest_by_station: Dict[str, Dict[str, Any]] = {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("stn_nam-value")
        ts = props.get("date_tm-value")
        if not name or not ts:
            continue
        existing = latest_by_station.get(name)
        if existing is None or ts > existing["properties"]["date_tm-value"]:
            latest_by_station[name] = feature

    if not latest_by_station:
        return None

    best_name, best_feature, best_distance = None, None, math.inf
    for name, feature in latest_by_station.items():
        coords = feature["geometry"]["coordinates"]
        station_lon, station_lat = coords[0], coords[1]
        distance = haversine_km(latitude, longitude, station_lat, station_lon)
        if distance < best_distance:
            best_name, best_feature, best_distance = name, feature, distance

    if best_feature is None or best_distance > search_radius_km:
        return None

    props = best_feature["properties"]
    coords = best_feature["geometry"]["coordinates"]
    rain_rate = props.get("pcpn_amt_pst1hr")  # mm accumulated in the past hour; not every station reports this
    reports_precipitation = rain_rate is not None
    observation = WeatherObservation(
        latitude=coords[1],
        longitude=coords[0],
        timestamp=props["date_tm-value"],
        # WeatherObservation.rain_rate_mm_h is a required float (calculate_exposure
        # depends on that guarantee elsewhere) -- 0.0 here is a technical
        # placeholder, never a claim of "zero rain". `reports_precipitation`
        # is the authoritative signal; callers must check it, not this field,
        # before treating the value as real evidence.
        rain_rate_mm_h=float(rain_rate) if reports_precipitation else 0.0,
        source=f"{SOURCE_STATION} -- {best_name}",
        site_id=best_name,
    )
    return observation, round(best_distance, 2), reports_precipitation


def get_radar_precipitation(latitude: float, longitude: float, timeout: float = 15.0) -> Optional[WeatherObservation]:
    """Radar-estimated rain rate (mm/h) at (latitude, longitude), via a
    real WMS ``GetFeatureInfo`` point query against the live radar mosaic.

    Returns ``None`` on any request failure or if the service has no data
    at this point (rather than guessing a value). A returned observation
    with ``rain_rate_mm_h == 0.0`` is a real "no precipitation detected"
    reading, not a missing value -- the radar service is queryable and
    answered.
    """
    import requests

    half_deg = 0.05  # ~5 km box around the point; the mosaic is 1 km resolution
    bbox = f"{longitude - half_deg},{latitude - half_deg},{longitude + half_deg},{latitude + half_deg}"
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": RADAR_LAYER,
        "QUERY_LAYERS": RADAR_LAYER,
        "CRS": "CRS:84",
        "BBOX": bbox,
        "WIDTH": 101,
        "HEIGHT": 101,
        "I": 50,
        "J": 50,
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": 1,
    }
    try:
        resp = requests.get(RADAR_WMS_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    features: List[Dict[str, Any]] = data.get("features", [])
    if not features:
        return None
    props = features[0].get("properties", {})
    value = props.get("value")
    if value is None:
        return None

    return WeatherObservation(
        latitude=latitude,
        longitude=longitude,
        timestamp=props.get("time", ""),
        rain_rate_mm_h=float(value),
        source=SOURCE_RADAR,
    )
