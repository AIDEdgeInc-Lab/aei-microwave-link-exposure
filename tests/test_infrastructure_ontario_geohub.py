"""Tests use real (verified live, captured 2026-09) and synthetic-but-schema-
accurate ArcGIS feature records -- no network access, fully deterministic."""

import pytest

from aei_mw_exposure import Provenance
from aei_mw_exposure.infrastructure.ontario_geohub import (
    is_relevant,
    load_towers,
    parse_tower_feature,
)

# Captured live from the Ontario GeoHub Tower layer (GTA bbox query) --
# most descriptive fields are genuinely null for this record, which is the
# normal case in this dataset, not a parsing failure.
REAL_SPARSE_RECORD = {
    "attributes": {
        "OGF_ID": 1200839745,
        "CLASS_SUBTYPE": "Communication Tower",
        "TOWER_IDENT": None,
        "OFFICIAL_NAME": None,
        "PURPOSE_OF_TOWER_DESCR": None,
        "RADIO_CALL_SIGN": None,
        "HEIGHT_ABOVE_GROUND_NUM": None,
        "GROUND_ELEV_ASL_NUM": None,
        "TOWER_CONSTRUCTION_DATE": None,
        "LOCATION_ACCURACY": "Within 10 metres",
        "OBJECTID": 1711,
    },
    "geometry": {"x": -79.8519551, "y": 43.5374084},
}

# Synthetic-but-schema-accurate record with every optional field populated,
# to verify the metadata-copy path actually copies present values.
FULLY_POPULATED_FIXTURE = {
    "attributes": {
        "OGF_ID": 999999,
        "CLASS_SUBTYPE": "Microwave Tower",
        "TOWER_IDENT": "T-0042",
        "OFFICIAL_NAME": "Test Hill Relay",
        "RADIO_CALL_SIGN": "VE3TEST",
        "HEIGHT_ABOVE_GROUND_NUM": 45.0,
        "GROUND_ELEV_ASL_NUM": 210,
        "TOWER_CONSTRUCTION_DATE": 946684800000,
        "LOCATION_ACCURACY": "Within 10 metres",
        "OBJECTID": 42,
    },
    "geometry": {"x": -79.5, "y": 44.0},
}

IRRELEVANT_RECORD = {
    "attributes": {"CLASS_SUBTYPE": "Lighthouse", "OBJECTID": 5},
    "geometry": {"x": -79.0, "y": 44.5},
}

MISSING_GEOMETRY_RECORD = {
    "attributes": {"CLASS_SUBTYPE": "Communication Tower", "OBJECTID": 6},
    "geometry": {},
}


def test_sparse_real_record_parses_with_minimal_metadata():
    site = parse_tower_feature(REAL_SPARSE_RECORD)
    assert site.provenance is Provenance.REAL
    assert site.latitude == pytest.approx(43.5374084)
    assert site.longitude == pytest.approx(-79.8519551)
    assert site.metadata == {"tower_class": "Communication Tower", "location_accuracy": "Within 10 metres"}
    # Null fields must NOT appear as keys at all -- never invent a value.
    assert "height_above_ground_m" not in site.metadata
    assert "radio_call_sign" not in site.metadata


def test_fully_populated_fixture_copies_every_present_field():
    site = parse_tower_feature(FULLY_POPULATED_FIXTURE)
    assert site.metadata["tower_class"] == "Microwave Tower"
    assert site.metadata["official_name"] == "Test Hill Relay"
    assert site.metadata["radio_call_sign"] == "VE3TEST"
    assert site.metadata["height_above_ground_m"] == 45.0
    assert site.metadata["ground_elevation_m"] == 210
    assert site.name == "Test Hill Relay"  # OFFICIAL_NAME used when present


def test_name_falls_back_when_official_name_missing():
    site = parse_tower_feature(REAL_SPARSE_RECORD)
    assert "Communication Tower" in site.name
    assert "1200839745" in site.name


def test_missing_geometry_raises_value_error():
    with pytest.raises(ValueError):
        parse_tower_feature(MISSING_GEOMETRY_RECORD)


def test_is_relevant_filters_by_class_subtype():
    assert is_relevant(REAL_SPARSE_RECORD) is True
    assert is_relevant(FULLY_POPULATED_FIXTURE) is True
    assert is_relevant(IRRELEVANT_RECORD) is False


def test_load_towers_skips_irrelevant_and_invalid_without_raising():
    sites, skipped = load_towers([REAL_SPARSE_RECORD, IRRELEVANT_RECORD, MISSING_GEOMETRY_RECORD, FULLY_POPULATED_FIXTURE])
    assert len(sites) == 2  # sparse + fully populated; lighthouse filtered, missing-geometry skipped
    assert len(skipped) == 1
    assert "6" in skipped[0]  # names the OBJECTID that failed


def test_no_link_is_ever_constructed_by_this_module():
    """Data-integrity guard: this adapter's public surface produces sites
    only. If a future change adds a link-producing function here, this
    test should be updated deliberately -- not pass by accident."""
    import aei_mw_exposure.infrastructure.ontario_geohub as mod

    assert not hasattr(mod, "MicrowaveLink")
    public_names = [n for n in dir(mod) if not n.startswith("_")]
    assert all("link" not in n.lower() for n in public_names)
