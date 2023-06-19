import pytest

from aistweet.geometry import center_coordinates, crossing_time_and_depth


def test_center_coordinates():
    assert center_coordinates(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0) == (
        pytest.approx(0.0),
        pytest.approx(0.0),
    )
