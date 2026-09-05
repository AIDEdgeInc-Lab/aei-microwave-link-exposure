import math

import pytest

from aei_mw_exposure.geometry import haversine_km


def test_zero_distance_for_identical_points():
    assert haversine_km(43.65, -79.38, 43.65, -79.38) == pytest.approx(0.0, abs=1e-9)


def test_known_distance_toronto_to_ottawa():
    # CN Tower, Toronto -> Parliament Hill, Ottawa. Real-world distance is
    # ~350-360 km straight-line; assert a wide, defensible band rather than
    # a manufactured precise figure.
    d = haversine_km(43.6426, -79.3871, 45.4236, -75.7003)
    assert 340.0 < d < 370.0


def test_symmetric():
    d1 = haversine_km(43.65, -79.38, 43.78, -79.23)
    d2 = haversine_km(43.78, -79.23, 43.65, -79.38)
    assert d1 == pytest.approx(d2)


def test_antipodal_points_half_earth_circumference():
    d = haversine_km(0.0, 0.0, 0.0, 180.0)
    assert d == pytest.approx(math.pi * 6371.0088, rel=1e-3)
