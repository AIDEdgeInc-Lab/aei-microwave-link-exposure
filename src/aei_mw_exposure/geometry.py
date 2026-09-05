"""Plain geodesic geometry. No domain knowledge, no dependencies."""

from __future__ import annotations

import math

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    r1, o1, r2, o2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = r2 - r1, o2 - o1
    h = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))
