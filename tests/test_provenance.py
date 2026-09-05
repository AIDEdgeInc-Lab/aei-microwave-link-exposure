from aei_mw_exposure import Provenance


def test_expected_members_exist():
    assert {p.value for p in Provenance} == {"real", "derived", "demo", "not_available", "user_provided"}


def test_is_a_string_subclass_for_easy_serialization():
    assert Provenance.REAL == "real"
    assert isinstance(Provenance.REAL, str)
    assert Provenance.REAL.value == "real"


def test_members_are_distinct():
    assert len(set(Provenance)) == 5


def test_user_provided_is_distinct_from_real_and_demo():
    """The whole reason this member exists: an uploaded site must never
    collapse into REAL (reserved for cited public sources) or DEMO
    (reserved for synthetic/illustrative data)."""
    assert Provenance.USER_PROVIDED != Provenance.REAL
    assert Provenance.USER_PROVIDED != Provenance.DEMO
