"""Ontario GeoHub -- "Tower" dataset (MNRF), Open Government Licence - Ontario.

Live service (verified against the actual API, not just its documentation):
https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open10/MapServer/14

WHAT THIS SOURCE CONFIRMS
--------------------------
A point location and a structure classification (``CLASS_SUBTYPE``) for
physical towers across Ontario -- e.g. "Communication Tower", "Microwave
Tower", "Radio Tower", plus non-telecom categories (lighthouses, fire
towers, ...) filtered out by ``RELEVANT_CLASS_SUBTYPES`` below. Checked
live against the GTA/York Region bounding box used by this project: every
tower there is classified "Communication Tower" -- none are classified
"Microwave Tower" specifically in this area, even though that category
exists elsewhere in the province. This module reports the source's own
classification string as-is; it does not upgrade "Communication Tower" to
"microwave" on its own judgement.

WHAT THIS SOURCE DOES NOT CONFIRM
-----------------------------------
Which equipment is on a given tower, which other tower (if any) it forms
a point-to-point link with, frequency, or ownership. Most descriptive
fields (height, elevation, construction date, radio call sign) are
NULL for the majority of records actually returned for this region --
this module only includes a metadata key when the source actually
populated it. Do not assume a field exists.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from ..microwave import MicrowaveSite
from ..provenance import Provenance
from ._arcgis import query_arcgis_layer

LAYER_QUERY_URL = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open10/MapServer/14/query"
)
SOURCE_NAME = "Ontario GeoHub -- Tower dataset (MNRF)"
LICENSE_URL = "https://www.ontario.ca/page/open-government-licence-ontario"

# The full CLASS_SUBTYPE vocabulary (confirmed live) also includes
# Lighthouse, Navigation Beacon, Fire Tower, Lightning Locator, and
# Meteorological Tower -- excluded here as not telecom-relevant.
RELEVANT_CLASS_SUBTYPES = {"Communication Tower", "Microwave Tower", "Radio Tower"}

# ArcGIS attribute name -> (metadata key, unit note). Only populated
# (non-null) values are copied into MicrowaveSite.metadata.
_METADATA_FIELDS = {
    "CLASS_SUBTYPE": "tower_class",
    "HEIGHT_ABOVE_GROUND_NUM": "height_above_ground_m",
    "GROUND_ELEV_ASL_NUM": "ground_elevation_m",
    "RADIO_CALL_SIGN": "radio_call_sign",
    "TOWER_CONSTRUCTION_DATE": "construction_date",
    "LOCATION_ACCURACY": "location_accuracy",
    "OFFICIAL_NAME": "official_name",
}


def is_relevant(feature: Dict[str, Any]) -> bool:
    """True if this feature's published CLASS_SUBTYPE is telecom-relevant."""
    attrs = feature.get("attributes", {})
    return attrs.get("CLASS_SUBTYPE") in RELEVANT_CLASS_SUBTYPES


def parse_tower_feature(feature: Dict[str, Any]) -> MicrowaveSite:
    """One raw ArcGIS feature (``{"attributes": {...}, "geometry": {"x", "y"}}``)
    -> one REAL ``MicrowaveSite``.

    Raises ``ValueError`` if the feature has no usable geometry or
    identifier -- callers doing a batch load should catch this per-record
    (see ``load_towers``) rather than let one bad record abort the batch.
    """
    attrs = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    lon, lat = geometry.get("x"), geometry.get("y")
    if lon is None or lat is None:
        raise ValueError(f"feature has no point geometry: OBJECTID={attrs.get('OBJECTID')}")

    object_id = attrs.get("OBJECTID")
    tower_ident = attrs.get("TOWER_IDENT")
    if object_id is None and not tower_ident:
        raise ValueError("feature has neither OBJECTID nor TOWER_IDENT to build a stable id")
    site_id = f"geohub-{tower_ident or object_id}"

    name = attrs.get("OFFICIAL_NAME") or f"{attrs.get('CLASS_SUBTYPE', 'Tower')} (OGF {attrs.get('OGF_ID', object_id)})"

    metadata: Dict[str, Any] = {}
    for field_name, meta_key in _METADATA_FIELDS.items():
        value = attrs.get(field_name)
        if value is not None:
            metadata[meta_key] = value

    return MicrowaveSite(
        id=site_id,
        name=name,
        latitude=float(lat),
        longitude=float(lon),
        provenance=Provenance.REAL,
        source=SOURCE_NAME,
        metadata=metadata,
    )


def load_towers(features: Iterable[Dict[str, Any]]) -> Tuple[List[MicrowaveSite], List[str]]:
    """Normalize a batch of raw features, filtering to telecom-relevant
    subtypes. Returns ``(sites, skipped)`` -- ``skipped`` names every
    record that couldn't be parsed and why, rather than silently dropping
    it.
    """
    sites: List[MicrowaveSite] = []
    skipped: List[str] = []
    for feature in features:
        if not is_relevant(feature):
            continue
        try:
            sites.append(parse_tower_feature(feature))
        except ValueError as exc:
            skipped.append(str(exc))
    return sites, skipped


def fetch_towers(bbox: Tuple[float, float, float, float], timeout: float = 15.0):
    """Live query for towers within ``bbox`` = (min_lon, min_lat, max_lon, max_lat).

    Returns an ``ArcGISQueryResult`` (``.features``, ``.exceeded_transfer_limit``).
    Requires ``requests`` (the ``infrastructure`` extra). This is a normal,
    official Government of Ontario service (``ws.lioservices.lrc.gov.on.ca``)
    -- current at time of writing, unlike the ISED mirror in ``ised.py``.
    """
    return query_arcgis_layer(LAYER_QUERY_URL, bbox, timeout=timeout)


def load_towers_in_bbox(
    bbox: Tuple[float, float, float, float], timeout: float = 15.0
) -> Tuple[List[MicrowaveSite], List[str], bool]:
    """Convenience: fetch + normalize in one call.

    Returns ``(sites, skipped, exceeded_transfer_limit)``. When the last
    element is True, the server truncated results at its own record limit
    -- the real count for this bbox is higher than ``len(sites)`` implies.
    Callers must surface this, not silently show a partial count as complete.
    """
    result = fetch_towers(bbox, timeout=timeout)
    sites, skipped = load_towers(result.features)
    return sites, skipped, result.exceeded_transfer_limit
