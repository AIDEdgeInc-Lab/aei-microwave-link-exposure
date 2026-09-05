"""ISED "Spectrum Licences Site Data" -- Open Government Licence - Canada.

Live service (verified against the actual API, not just its documentation):
https://services.arcgis.com/wjcPoefzjpzCgffS/ArcGIS/rest/services/Spectrum_Licences_Site_Data/FeatureServer/0

Hosted by Esri Canada from ISED's Spectrum Management System data extract.
Attribution per the service's own metadata: "Innovation, Science, and
Economic Development Canada (ISED); Government of Canada", licensed under
the Open Government Licence - Canada.

WHAT THIS SOURCE ACTUALLY IS -- READ BEFORE USING
---------------------------------------------------
This is **cellular/mobile network spectrum-licensee site data** (real
records checked in the GTA/York Region: Freedom Mobile sites on AWS-3,
AWS, and 600 MHz bands), NOT point-to-point microwave station data. ISED
does publish a separate "Fixed Service" extract (part of its Spectrum
Management System Authorization Data Extract, on open.canada.ca) that
would be the relevant one for microwave backhaul stations specifically --
that dataset is CSV-only with no live query API found during this
project's research, and is not wired up here. Do not label sites from
this module as "microwave sites"; they are cellular/mobile base station
sites, which is a different (still real, still legitimate) kind of
telecom infrastructure.

This mirror's own item metadata also states it is updated only twice a
year (last currency check: Jan 2024 per the source) and is flagged
"deprecated" by its host as of this project's research. Treat it as
best-effort, not a guaranteed-fresh feed -- callers should degrade
gracefully if it's unavailable.

ONE ROW IS ONE CHANNEL, NOT ONE PHYSICAL SITE -- READ BEFORE USING
---------------------------------------------------------------------
Verified live: the same physical location (same LOCATION string, same
coordinates) commonly appears as multiple rows, one per licensed
frequency channel -- e.g. one Freedom Mobile site had separate rows for
its AWS and 600 MHz channels. Treating each row as a distinct "site"
would silently inflate a real site count into a real *channel* count.
``load_sites``/``load_sites_in_bbox`` therefore group rows by rounded
coordinate (~1m precision) into one ``MicrowaveSite`` per physical
location before returning -- see ``group_features_by_location`` and
``merge_group``. ``parse_site_feature`` (single-row, no grouping) is kept
for callers who genuinely want per-channel records.

WHAT THIS SOURCE DOES NOT CONFIRM
-----------------------------------
Any point-to-point link, or that a site's transmit/receive frequency pair
implies a fixed microwave hop rather than an ordinary cellular duplex
channel. Per-site metadata (licensee, bands, structure height, antenna
azimuth) is real, but this module still only copies fields the source
actually populated.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from ..microwave import MicrowaveSite
from ..provenance import Provenance
from ._arcgis import query_arcgis_layer

LAYER_QUERY_URL = (
    "https://services.arcgis.com/wjcPoefzjpzCgffS/ArcGIS/rest/services/Spectrum_Licences_Site_Data/FeatureServer/0/query"
)
SOURCE_NAME = "ISED Spectrum Licences Site Data (cellular/mobile), via Esri Canada mirror"
LICENSE_URL = "https://open.canada.ca/en/open-government-licence-canada"

# Coordinate rounding used to group per-channel rows into one physical
# site: 5 decimal degrees is ~1.1m at this latitude -- rows this close are
# the same structure, not two nearby ones.
_COORD_GROUPING_DECIMALS = 5

# Fields that describe the physical STRUCTURE (constant across channels at
# one site) -> take the first non-null value seen in the group.
_STRUCTURAL_FIELDS = {
    "SITE_ELEV": "site_elevation_m",
    "STUCT_HT": "structure_height_m",  # sic -- the live field is misspelled, not the docs
    "TX_ANT_HT": "antenna_height_m",
}

# Per-CHANNEL fields (genuinely differ row to row at the same site) -> the
# merged site reports the range across the group, not one arbitrary value.
_PER_CHANNEL_RANGE_FIELDS = {
    "TRANSMIT_FREQ": "transmit_freq_mhz",
    "RECEIVE_FREQ": "receive_freq_mhz",
    "TX_ANT_AZIM": "antenna_azimuth_deg",
}


def parse_site_feature(feature: Dict[str, Any]) -> MicrowaveSite:
    """One raw ArcGIS feature (one CHANNEL row) -> one REAL ``MicrowaveSite``.

    For most uses prefer ``load_sites``, which groups channel rows into
    one site per physical location -- this function does not group.
    Raises ``ValueError`` if latitude/longitude are missing.
    """
    attrs = feature.get("attributes") or {}
    lat, lon = _extract_coords(feature)
    if lat is None or lon is None:
        raise ValueError(f"feature has no coordinates: OBJECTID={attrs.get('OBJECTID')}")

    object_id = attrs.get("OBJECTID")
    licensee = attrs.get("LICENSEE")
    location = attrs.get("LOCATION")
    name = f"{licensee or 'Unknown licensee'} -- {location}" if location else (licensee or f"ISED site {object_id}")

    metadata: Dict[str, Any] = {}
    if licensee is not None:
        metadata["licensee"] = licensee
    if attrs.get("SERVICE") is not None:
        metadata["service_band"] = attrs["SERVICE"]
    for field_name, meta_key in {**_STRUCTURAL_FIELDS, **_PER_CHANNEL_RANGE_FIELDS}.items():
        value = attrs.get(field_name)
        if value is not None:
            metadata[meta_key] = value

    return MicrowaveSite(
        id=f"ised-{object_id}",
        name=name,
        latitude=lat,
        longitude=lon,
        provenance=Provenance.REAL,
        source=SOURCE_NAME,
        metadata=metadata,
    )


def _extract_coords(feature: Dict[str, Any]):
    attrs = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    lon, lat = geometry.get("x"), geometry.get("y")
    if lon is None or lat is None:
        lat, lon = attrs.get("LATITUDE"), attrs.get("LONGITUDE")
    if lon is None or lat is None:
        return None, None
    return float(lat), float(lon)


def group_features_by_location(features: Iterable[Dict[str, Any]]) -> Dict[Tuple[float, float], List[Dict[str, Any]]]:
    """Group raw channel-level rows by rounded coordinate."""
    groups: Dict[Tuple[float, float], List[Dict[str, Any]]] = {}
    for feature in features:
        lat, lon = _extract_coords(feature)
        if lat is None or lon is None:
            continue
        key = (round(lat, _COORD_GROUPING_DECIMALS), round(lon, _COORD_GROUPING_DECIMALS))
        groups.setdefault(key, []).append(feature)
    return groups


def merge_group(key: Tuple[float, float], group: List[Dict[str, Any]]) -> MicrowaveSite:
    """One physical site from N channel rows sharing the same coordinate."""
    lat, lon = key
    attrs_list = [f.get("attributes") or {} for f in group]
    first = attrs_list[0]

    licensees = sorted({a["LICENSEE"] for a in attrs_list if a.get("LICENSEE")})
    location = first.get("LOCATION")
    licensee_label = " / ".join(licensees) if licensees else "Unknown licensee"
    name = f"{licensee_label} -- {location}" if location else licensee_label

    metadata: Dict[str, Any] = {"channel_count": len(group)}
    if licensees:
        metadata["licensee"] = " / ".join(licensees)
    bands = sorted({a["SERVICE"] for a in attrs_list if a.get("SERVICE")})
    if bands:
        metadata["service_bands"] = ", ".join(bands)

    for field_name, meta_key in _STRUCTURAL_FIELDS.items():
        value = next((a[field_name] for a in attrs_list if a.get(field_name) is not None), None)
        if value is not None:
            metadata[meta_key] = value

    for field_name, meta_key in _PER_CHANNEL_RANGE_FIELDS.items():
        values = [a[field_name] for a in attrs_list if a.get(field_name) is not None]
        if not values:
            continue
        metadata[f"{meta_key}_range"] = f"{min(values):g}-{max(values):g}" if min(values) != max(values) else f"{min(values):g}"

    object_id = first.get("OBJECTID")
    return MicrowaveSite(
        id=f"ised-{object_id}",
        name=name,
        latitude=lat,
        longitude=lon,
        provenance=Provenance.REAL,
        source=SOURCE_NAME,
        metadata=metadata,
    )


def load_sites(features: Iterable[Dict[str, Any]]) -> Tuple[List[MicrowaveSite], List[str]]:
    """Group channel-level rows into one ``MicrowaveSite`` per physical
    location, then normalize. Returns ``(sites, skipped)`` -- ``skipped``
    names rows that had no usable coordinates at all."""
    features = list(features)
    skipped = [
        f"OBJECTID={((f.get('attributes') or {}).get('OBJECTID'))}: no coordinates"
        for f in features
        if _extract_coords(f) == (None, None)
    ]
    groups = group_features_by_location(features)
    sites = [merge_group(key, group) for key, group in groups.items()]
    return sites, skipped


def fetch_sites(bbox: Tuple[float, float, float, float], timeout: float = 15.0):
    """Live query for channel-level rows within ``bbox`` = (min_lon, min_lat, max_lon, max_lat).

    Returns an ``ArcGISQueryResult`` (``.features``, ``.exceeded_transfer_limit``).
    Requires ``requests`` (the ``infrastructure`` extra). See the module
    docstring: this mirror is host-flagged deprecated and semi-annually
    updated -- callers should not treat a failure here as unexpected.
    ``maxRecordCount`` on this service is 1000 rows per request (confirmed
    live: a single GTA-wide query legitimately exceeds this and comes back
    with ``exceededTransferLimit: true``) -- no pagination loop is
    implemented for this best-effort secondary layer; see
    ``load_sites_in_bbox``, which propagates the flag rather than hiding it.
    """
    return query_arcgis_layer(LAYER_QUERY_URL, bbox, timeout=timeout)


def load_sites_in_bbox(
    bbox: Tuple[float, float, float, float], timeout: float = 15.0
) -> Tuple[List[MicrowaveSite], List[str], bool]:
    """Convenience: fetch + group + normalize in one call.

    Returns ``(sites, skipped, exceeded_transfer_limit)``. When the last
    element is True, the server truncated raw channel rows at its own
    limit *before* grouping -- the real site count for this bbox may be
    higher than ``len(sites)`` implies. Callers must surface this.
    """
    result = fetch_sites(bbox, timeout=timeout)
    sites, skipped = load_sites(result.features)
    return sites, skipped, result.exceeded_transfer_limit
