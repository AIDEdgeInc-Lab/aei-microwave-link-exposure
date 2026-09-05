import pytest

from aei_mw_exposure import Provenance
from demo.user_sites import MAX_USER_SITES, parse_user_sites_csv

VALID_CSV = """site_id,name,latitude,longitude
NW-001,North Site,44.3500,-79.7000
NW-002,Barrie West,44.3800,-79.7600
NW-003,South Site,44.2000,-79.6500
"""


def test_valid_csv_parses_all_rows():
    sites, errors = parse_user_sites_csv(VALID_CSV)
    assert len(sites) == 3
    assert errors == []
    assert [s.id for s in sites] == ["NW-001", "NW-002", "NW-003"]
    assert sites[0].name == "North Site"
    assert sites[0].latitude == pytest.approx(44.35)
    assert sites[0].longitude == pytest.approx(-79.70)


def test_valid_sites_carry_user_provided_provenance_not_real_or_demo():
    sites, _ = parse_user_sites_csv(VALID_CSV)
    for s in sites:
        assert s.provenance is Provenance.USER_PROVIDED
        assert s.provenance is not Provenance.REAL
        assert s.provenance is not Provenance.DEMO
        assert "not independently verified" in s.source


def test_missing_required_column_raises():
    csv_text = "site_id,name,latitude\nNW-001,North,44.35\n"
    with pytest.raises(ValueError, match="longitude"):
        parse_user_sites_csv(csv_text)


def test_empty_file_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_user_sites_csv("")
    with pytest.raises(ValueError, match="empty"):
        parse_user_sites_csv("   \n  ")


def test_header_only_file_produces_no_sites_and_no_errors():
    sites, errors = parse_user_sites_csv("site_id,name,latitude,longitude\n")
    assert sites == []
    assert errors == []


def test_invalid_coordinates_are_skipped_and_reported():
    csv_text = (
        "site_id,name,latitude,longitude\n"
        "NW-001,Good,44.35,-79.70\n"
        "NW-002,Bad Lat,not-a-number,-79.70\n"
        "NW-003,Bad Lon,44.35,also-bad\n"
    )
    sites, errors = parse_user_sites_csv(csv_text)
    assert [s.id for s in sites] == ["NW-001"]
    assert len(errors) == 2
    assert "Row 3" in errors[0] and "numeric" in errors[0]
    assert "Row 4" in errors[1] and "numeric" in errors[1]


def test_out_of_range_coordinates_are_skipped_and_reported():
    csv_text = "site_id,name,latitude,longitude\nNW-001,Bad,91.0,-79.70\n"
    sites, errors = parse_user_sites_csv(csv_text)
    assert sites == []
    assert len(errors) == 1
    assert "NW-001" in errors[0]


def test_duplicate_site_id_is_skipped_and_reported():
    csv_text = (
        "site_id,name,latitude,longitude\n"
        "NW-001,First,44.35,-79.70\n"
        "NW-001,Second,44.40,-79.60\n"
    )
    sites, errors = parse_user_sites_csv(csv_text)
    assert len(sites) == 1
    assert sites[0].name == "First"
    assert len(errors) == 1
    assert "duplicate" in errors[0].lower()


def test_empty_site_id_is_skipped_and_reported():
    csv_text = "site_id,name,latitude,longitude\n,Nameless,44.35,-79.70\n"
    sites, errors = parse_user_sites_csv(csv_text)
    assert sites == []
    assert len(errors) == 1
    assert "empty site_id" in errors[0]


def test_blank_name_falls_back_to_site_id():
    csv_text = "site_id,name,latitude,longitude\nNW-001,,44.35,-79.70\n"
    sites, errors = parse_user_sites_csv(csv_text)
    assert errors == []
    assert sites[0].name == "NW-001"


def test_upload_cap_stops_processing_and_reports_remainder():
    rows = "\n".join(f"S{i},Site {i},44.{i:02d},-79.{i:02d}" for i in range(MAX_USER_SITES + 5))
    csv_text = "site_id,name,latitude,longitude\n" + rows + "\n"
    sites, errors = parse_user_sites_csv(csv_text)
    assert len(sites) == MAX_USER_SITES
    assert any("Stopped after" in e for e in errors)


def test_example_csv_served_by_the_explorer_is_itself_valid():
    """app.py offers examples/my_sites_example.csv directly via a
    'Download example CSV' button -- this pins that the file it serves
    actually parses cleanly, so a stale/broken example is never shipped
    as a user's first experience of the workflow."""
    from pathlib import Path

    example_path = Path(__file__).resolve().parent.parent / "examples" / "my_sites_example.csv"
    assert example_path.exists(), "examples/my_sites_example.csv is missing"

    sites, errors = parse_user_sites_csv(example_path.read_text())
    assert errors == []
    assert len(sites) >= 1
    for site in sites:
        assert site.provenance is Provenance.USER_PROVIDED
