from trip_fixtures import rec

from trip.domain.traits import compared_places
from trip.infrastructure.catalog import Catalog


def cat():
    return Catalog.from_records([
        rec(1, "Cà Phê Ồn Ào Phố Núi", {"noise": ("loud", 12), "crowd": ("high", 8), "scenic_view": ("present", 3)}),
        rec(2, "Cà Phê Một", {"noise": ("quiet", 9), "crowd": ("low", 4), "scenic_view": ("present", 5)}),
        rec(3, "Cà Phê Hai", {"noise": ("quiet", 7), "crowd": ("low", 3), "scenic_view": ("present", 6)}),
    ], n_min=1)


def test_distinctive_traits_of_the_named_place():
    out = compared_places("mình không thích quán giống Cà Phê Ồn Ào Phố Núi", cat())
    assert out[0]["name"] == "Cà Phê Ồn Ào Phố Núi"
    assert out[0]["traits"] == [{"feature": "noise", "value": "loud", "n": 12}, {"feature": "crowd", "value": "high", "n": 8}]


def test_no_cue_or_unknown_place_gives_nothing():
    assert compared_places("muốn yên tĩnh hơn", cat()) == []
    assert compared_places("không thích quán giống Highlands", cat()) == []
