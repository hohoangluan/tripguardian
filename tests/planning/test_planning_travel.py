from plan_fixtures import fake_matrix

from live import Unavailable
from planning import settings
from planning.travel import build_travel, km, rough_minutes, walk_minutes

CFG = settings.load(settings.PATH)
A, B, C = (11.9404, 108.4583), (11.9404, 108.4600), (11.9029, 108.4482)   # B is ~190 m from A; C is ~4 km away


def test_a_short_leg_is_walked_and_a_long_one_uses_the_matrix():
    t = build_travel({"a": A, "b": B, "c": C}, "motorbike", CFG, None, fake_matrix)
    assert t.leg("a", "b") == (walk_minutes(km(A, B), CFG), "walk")
    assert t.leg("a", "c")[1] == "motorbike" and t.leg("a", "c")[0] == fake_matrix([A, C], None, None)["minutes"][0][1]
    assert t.leg("a", "a") == (0, "none")
    assert (t.source, t.rough_pairs) == ("osrm", 0)


def test_a_dead_osrm_makes_the_whole_matrix_rough_and_says_so():
    def dead(points, mode, cfg):
        raise Unavailable("osrm down")

    t = build_travel({"a": A, "c": C}, "car", CFG, None, dead)
    assert t.source == "rough" and t.fetched_at is None
    assert t.leg("a", "c")[0] == rough_minutes(km(A, C), "car", CFG)


def test_one_pair_without_a_road_is_rough_and_counted_while_the_rest_stays_osrm():
    def holes(points, mode, cfg):
        m = fake_matrix(points, mode, cfg)
        m["minutes"][0][2] = None
        return m

    t = build_travel({"a": A, "b": B, "c": C}, "motorbike", CFG, None, holes)
    assert t.source == "osrm" and t.rough_pairs == 1
    assert t.leg("a", "c")[0] == rough_minutes(km(A, C), "motorbike", CFG)
    assert t.leg("c", "a")[0] == fake_matrix([A, B, C], None, None)["minutes"][2][0]


def test_a_single_node_needs_no_matrix():
    t = build_travel({"a": A}, None, CFG, None, lambda *a: (_ for _ in ()).throw(AssertionError("no call")))
    assert t.leg("a", "a") == (0, "none")
