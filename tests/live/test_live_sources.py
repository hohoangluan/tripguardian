"""Real network and a real local OSRM: python -m pytest -m live tests/live/test_live_sources.py -s"""

import pytest

from live import settings
from live.osrm import travel_matrix

pytestmark = pytest.mark.live

DALAT = [(11.9465, 108.4419), (11.9029, 108.4482)]  # Hồ Xuân Hương, Thung lũng Tình yêu area


def test_osrm_answers_for_two_points_in_dalat():
    m = travel_matrix(DALAT, "motorbike", settings.load())
    assert m["source"] == "osrm"
    assert 3 <= m["minutes"][0][1] <= 60, m["minutes"]


def test_nominatim_finds_a_place_in_dalat():
    from live.geocode import geocode
    p = geocode("Bến xe Liên tỉnh Đà Lạt", settings.load())
    assert p is not None
    assert 11.8 < p["lat"] < 12.1 and 108.3 < p["lng"] < 108.6, p
