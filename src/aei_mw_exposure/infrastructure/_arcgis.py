"""Shared ArcGIS REST query mechanics for infrastructure adapters.

Not part of the public API (leading underscore). Both current live sources
(Ontario GeoHub, ISED's Esri Canada mirror) happen to be ArcGIS-hosted, so
the HTTP/query-envelope mechanics are identical; only the field schema and
normalization differ per adapter -- that difference-only logic stays in
each adapter's own module, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ArcGISQueryResult:
    features: List[Dict[str, Any]]
    exceeded_transfer_limit: bool
    """True when the server's own response says it silently truncated
    results at its ``maxRecordCount`` -- i.e. more real records exist than
    were returned. Callers must surface this, not just the count they got,
    or a truncated result set can misleadingly look complete."""


def query_arcgis_layer(
    query_url: str,
    bbox: Tuple[float, float, float, float],
    timeout: float = 15.0,
) -> ArcGISQueryResult:
    """Query one ArcGIS FeatureServer/MapServer layer for features within
    ``bbox`` = (min_lon, min_lat, max_lon, max_lat), WGS84 in and out.

    Requires ``requests`` (the ``infrastructure`` extra) -- imported here,
    not at module level, so parsing-only use of an adapter never requires
    it installed.
    """
    import requests

    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "geometry": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "json",
    }
    resp = requests.get(query_url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS query to {query_url} failed: {data['error']}")
    return ArcGISQueryResult(
        features=data.get("features", []),
        exceeded_transfer_limit=bool(data.get("exceededTransferLimit", False)),
    )
