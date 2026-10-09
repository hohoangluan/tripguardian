import pytest
from trip_fixtures import MONDAY_CLOSED, rec

from trip.infrastructure.catalog import Catalog
from trip.infrastructure.settings import Settings


@pytest.fixture
def records():
    quiet = [rec(i, f"Quán Yên Tĩnh Số {i}", {"noise": ("quiet", 5), "long_stay_chill": ("present", 4),
                                               "crowd": ("low", 3)}) for i in range(1, 7)]
    loud = [rec(i, f"Quán Nhạc Sống {i}", {"noise": ("loud", 5), "live_music": ("present", 6),
                                            "crowd": ("high", 4)}) for i in range(7, 13)]
    steep = [rec(i, f"Đồi Dốc Cao {i}", {"steep_or_stairs": ("present", 3), "scenic_view": ("present", 9),
                                          "photo_spot": ("present", 4)}) for i in range(13, 17)]
    flat = [rec(17, "Vườn Phẳng Lặng Xanh", {"steep_or_stairs": ("absent", 2), "scenic_view": ("present", 3)},
                hours=MONDAY_CLOSED)]
    other = [rec(i, f"Chợ Phiên Đêm {i}", {"local_specialty_food": ("present", 5)}) for i in range(18, 22)]
    return quiet + loud + steep + flat + other


@pytest.fixture
def catalog(records):
    return Catalog.from_records(records, n_min=1, videos={"7565853238147255573": "0x11:0x1"})


@pytest.fixture
def cfg():
    return Settings(n_min=1, top_k=4, enough_factor=1.0)
