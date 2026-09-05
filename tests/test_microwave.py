import pytest

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance


def make_sites(provenance=Provenance.DEMO):
    a = MicrowaveSite(id="a", name="A", latitude=43.65, longitude=-79.38, provenance=provenance)
    b = MicrowaveSite(id="b", name="B", latitude=43.78, longitude=-79.23, provenance=provenance)
    return a, b


def test_link_length_is_derived_from_coordinates_not_hardcoded():
    a, b = make_sites()
    link = MicrowaveLink(
        id="l", site_a=a, site_b=b, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO
    )
    assert link.length_km > 0
    # Matches independently-computed haversine distance for the same points.
    from aei_mw_exposure.geometry import haversine_km

    assert link.length_km == pytest.approx(haversine_km(a.latitude, a.longitude, b.latitude, b.longitude))


def test_site_invalid_latitude_rejected():
    with pytest.raises(ValueError):
        MicrowaveSite(id="x", name="X", latitude=91.0, longitude=0.0, provenance=Provenance.DEMO)


def test_site_invalid_longitude_rejected():
    with pytest.raises(ValueError):
        MicrowaveSite(id="x", name="X", latitude=0.0, longitude=181.0, provenance=Provenance.DEMO)


def test_site_requires_explicit_provenance():
    with pytest.raises(TypeError):
        MicrowaveSite(id="x", name="X", latitude=0.0, longitude=0.0)  # type: ignore[call-arg]


def test_link_requires_explicit_provenance():
    a, b = make_sites()
    with pytest.raises(TypeError):
        MicrowaveLink(id="l", site_a=a, site_b=b, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0)  # type: ignore[call-arg]


def test_link_identical_endpoints_rejected():
    a = MicrowaveSite(id="same", name="A", latitude=43.65, longitude=-79.38, provenance=Provenance.DEMO)
    a2 = MicrowaveSite(id="same", name="A duplicate", latitude=43.66, longitude=-79.39, provenance=Provenance.DEMO)
    with pytest.raises(ValueError):
        MicrowaveLink(id="l", site_a=a, site_b=a2, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)


def test_link_invalid_frequency_rejected():
    a, b = make_sites()
    with pytest.raises(ValueError):
        MicrowaveLink(id="l", site_a=a, site_b=b, frequency_ghz=0.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)
    with pytest.raises(ValueError):
        MicrowaveLink(id="l", site_a=a, site_b=b, frequency_ghz=-5.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO)


def test_link_invalid_fade_margin_rejected():
    a, b = make_sites()
    with pytest.raises(ValueError):
        MicrowaveLink(id="l", site_a=a, site_b=b, frequency_ghz=18.0, polarization="V", fade_margin_db=0.0, provenance=Provenance.DEMO)


def test_link_invalid_polarization_rejected():
    a, b = make_sites()
    with pytest.raises(ValueError):
        MicrowaveLink(id="l", site_a=a, site_b=b, frequency_ghz=18.0, polarization="X", fade_margin_db=30.0, provenance=Provenance.DEMO)


def test_provenance_is_explicit_and_not_derived_from_endpoints():
    """A link's provenance is independent of its sites' provenance -- two
    REAL sites do not make a REAL link. Nothing in MicrowaveLink derives
    its own provenance from site_a/site_b, and this test pins that down."""
    a, b = make_sites(provenance=Provenance.REAL)
    link = MicrowaveLink(
        id="l", site_a=a, site_b=b, frequency_ghz=18.0, polarization="V", fade_margin_db=30.0, provenance=Provenance.DEMO
    )
    assert a.provenance is Provenance.REAL
    assert b.provenance is Provenance.REAL
    assert link.provenance is Provenance.DEMO


def test_site_metadata_defaults_to_empty_and_is_independent_per_instance():
    a, b = make_sites()
    assert a.metadata == {}
    a.metadata["x"] = 1
    assert b.metadata == {}  # default_factory, not a shared mutable default


def test_site_source_is_optional():
    site = MicrowaveSite(id="x", name="X", latitude=0.0, longitude=0.0, provenance=Provenance.REAL)
    assert site.source is None
    cited = MicrowaveSite(id="y", name="Y", latitude=0.0, longitude=0.0, provenance=Provenance.REAL, source="Some Agency")
    assert cited.source == "Some Agency"


@pytest.mark.parametrize("value", list(Provenance))
def test_all_provenance_values_are_constructible(value):
    site = MicrowaveSite(id="x", name="X", latitude=0.0, longitude=0.0, provenance=value)
    assert site.provenance is value
