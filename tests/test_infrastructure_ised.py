"""Tests use real records captured live from the ISED Spectrum Licences
Site Data mirror (GTA bbox query, 2026-09) -- no network access in tests."""

import pytest

from aei_mw_exposure import Provenance
from aei_mw_exposure.infrastructure.ised import group_features_by_location, load_sites, merge_group, parse_site_feature

# Captured live -- a real Freedom Mobile cellular site in the GTA bbox.
# Note this is CELLULAR spectrum (AWS-3 band, ~2.16 GHz), not microwave.
REAL_CELLULAR_RECORD = {
    "attributes": {
        "LICENSEE": "Freedom Mobile Inc.",
        "SERVICE": "AWS-3",
        "TRANSMIT_FREQ": 2162.5,
        "RECEIVE_FREQ": 1762.5,
        "LOCATION": "OTR0286-Toronto ON 15 Baif Boulevar",
        "PROV": "ON",
        "SITE_ELEV": 210,
        "STUCT_HT": 30,
        "TX_ANT_HT": 30,
        "TX_ANT_AZIM": 110,
        "OBJECTID": 12345,
    },
    "geometry": {"x": -79.43527777799994, "y": 43.85777777800007},
}

# Real pair captured live: the SAME physical site ("OTR0327 Markham 8920
# Woodbine Av", identical coordinates) licensed on two different bands --
# this is exactly the one-row-per-channel case this module must not treat
# as two separate real sites.
SAME_SITE_CHANNEL_A = {
    "attributes": {
        "LICENSEE": "Freedom Mobile Inc.", "SERVICE": "AWS", "TRANSMIT_FREQ": 2132.5, "RECEIVE_FREQ": 1732.5,
        "LOCATION": "OTR0327 Markham 8920 Woodbine Av", "SITE_ELEV": 188, "STUCT_HT": 22, "TX_ANT_HT": 22,
        "TX_ANT_AZIM": 0, "OBJECTID": 100,
    },
    "geometry": {"x": -79.36138888899995, "y": 43.85972222200007},
}
SAME_SITE_CHANNEL_B = {
    "attributes": {
        "LICENSEE": "Freedom Mobile Inc.", "SERVICE": "600B", "TRANSMIT_FREQ": 690.5, "RECEIVE_FREQ": 644.5,
        "LOCATION": "OTR0327 Markham 8920 Woodbine Av", "SITE_ELEV": 188, "STUCT_HT": 22, "TX_ANT_HT": 22,
        "TX_ANT_AZIM": 190, "OBJECTID": 101,
    },
    "geometry": {"x": -79.36138888899995, "y": 43.85972222200007},
}

MISSING_COORDINATES_RECORD = {
    "attributes": {"LICENSEE": "Nobody", "OBJECTID": 1},
    "geometry": {},
}


def test_single_row_parses_correctly():
    site = parse_site_feature(REAL_CELLULAR_RECORD)
    assert site.provenance is Provenance.REAL
    assert site.latitude == pytest.approx(43.85777777800007)
    assert "Freedom Mobile" in site.name
    assert site.metadata["licensee"] == "Freedom Mobile Inc."
    assert site.metadata["service_band"] == "AWS-3"


def test_this_is_labeled_cellular_not_microwave():
    """Data-integrity guard: this source is cellular/mobile spectrum data,
    and nothing in this module should claim otherwise."""
    import aei_mw_exposure.infrastructure.ised as mod

    assert "microwave" not in mod.SOURCE_NAME.lower()
    site = parse_site_feature(REAL_CELLULAR_RECORD)
    assert "microwave" not in site.name.lower()


def test_missing_coordinates_raises_value_error():
    with pytest.raises(ValueError):
        parse_site_feature(MISSING_COORDINATES_RECORD)


def test_grouping_merges_two_channel_rows_at_the_same_coordinate():
    groups = group_features_by_location([SAME_SITE_CHANNEL_A, SAME_SITE_CHANNEL_B])
    assert len(groups) == 1  # one physical site, not two
    (key, rows), = groups.items()
    assert len(rows) == 2


def test_load_sites_does_not_double_count_channels_as_sites():
    """The exact regression this module exists to prevent: two rows at one
    coordinate must produce ONE MicrowaveSite, not two."""
    sites, skipped = load_sites([SAME_SITE_CHANNEL_A, SAME_SITE_CHANNEL_B])
    assert len(sites) == 1
    site = sites[0]
    assert site.metadata["channel_count"] == 2
    assert "AWS" in site.metadata["service_bands"]
    assert "600B" in site.metadata["service_bands"]


def test_merged_site_reports_channel_frequency_range_not_one_arbitrary_value():
    groups = group_features_by_location([SAME_SITE_CHANNEL_A, SAME_SITE_CHANNEL_B])
    (key, rows), = groups.items()
    site = merge_group(key, rows)
    # Real values were 2132.5 and 690.5 MHz -- both ends of the range must appear.
    assert "690.5" in site.metadata["transmit_freq_mhz_range"]
    assert "2132.5" in site.metadata["transmit_freq_mhz_range"]


def test_merged_site_uses_structural_field_shared_across_channels():
    groups = group_features_by_location([SAME_SITE_CHANNEL_A, SAME_SITE_CHANNEL_B])
    (key, rows), = groups.items()
    site = merge_group(key, rows)
    assert site.metadata["structure_height_m"] == 22  # same physical structure, both rows agree


def test_load_sites_combines_distinct_and_shared_coordinates_correctly():
    sites, skipped = load_sites([REAL_CELLULAR_RECORD, SAME_SITE_CHANNEL_A, SAME_SITE_CHANNEL_B, MISSING_COORDINATES_RECORD])
    assert len(sites) == 2  # one distinct site + one merged two-channel site
    assert len(skipped) == 1


def test_no_link_is_ever_constructed_by_this_module():
    import aei_mw_exposure.infrastructure.ised as mod

    public_names = [n for n in dir(mod) if not n.startswith("_")]
    assert all("link" not in n.lower() for n in public_names)
