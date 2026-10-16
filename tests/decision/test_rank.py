from types import SimpleNamespace

from fixtures import feat, love, si, srec

from decision.model import Cand
from decision.rank import conf, preference, score, wants
from decision.settings import default

CFG = default()


def prof(**kw):
    return SimpleNamespace(**{"soft": [], "visited": [], "price_sensitivity": 0.0, **kw})


def test_conf_scales_with_authors_agreement_and_status():
    assert conf(feat("present", n=3)) == 1.0
    assert conf(feat("present", n=1)) == 1 / 3
    assert conf(feat("present", n=3, status="UNCERTAIN", agreement=0.8)) == 0.4


def test_preference_matches_context_and_counts_missing_wanted_features():
    s = si(soft_weights=[love("crowd", "low", context={"time_of_day": "morning"}), love("scenic_view")])
    rec = srec("A", features={"crowd": feat("high", by_context={"time_of_day=morning": {"low": 3, "high": 1}})})
    pref, unc, matches = preference(rec, wants(s, prof()))
    assert pref == 0.5 and unc == 0.5 and matches[0][:2] == ("crowd", "low")


def test_avoid_weight_is_negative_and_profile_soft_counts():
    s = si(soft_weights=[love("live_music", weight=-1)])
    p = prof(soft=[SimpleNamespace(feature="scenic_view", value="present", weight=1)])
    pref, _, _ = preference(srec("A", features={"live_music": "present", "scenic_view": "present"}), wants(s, p))
    assert pref == 0.0


def test_score_parts_novelty_experience_price():
    a = Cand(srec("A", voices=100, price={"min_vnd": 300000, "max_vnd": 300000}), "experience")
    b = Cand(srec("B", voices=10), "experience")
    a.fit = b.fit = 1.0
    s = si(context={"experience": "first"}, novelty={"level": "new", "visited": ["A"]})
    score([a, b], s, prof(price_sensitivity=1.0), CFG)
    assert a.parts["nov"] == -1.0 and b.parts["nov"] == 0.0
    assert a.parts["pop"] == 1.0 and b.parts["pop"] == 0.0 and a.parts["exp"] == 1.0
    assert a.parts["price"] == -1.0
    assert a.score == round(sum(CFG.weights[k] * v for k, v in a.parts.items()), 4)


def test_food_preferences_do_not_dilute_sightseeing_scores():
    park = srec("park", group="nature", usable=("experience",), features={"scenic_view": "present"})
    plain = wants(si(soft_weights=[love("scenic_view")]), prof())
    dietary = wants(si(soft_weights=[love("scenic_view"), love("vegetarian_options", "yes")]), prof())
    assert preference(park, dietary) == preference(park, plain)


from decision.wishes import build  # noqa: E402


def _meal(pid):
    return Cand(srec(pid, group="restaurant", category="Nhà hàng", usable=("meal",)), "meal")


def _dish(name, *ids):
    return {"dishes": [{"dish": name, "quote": name, "place_ids": list(ids)}], "kinds": [], "like": []}


def _run(cands, s):
    for c in cands:
        c.fit = 1.0
    score(cands, s, prof(), CFG, wishes=build(s, [c.rec for c in cands], CFG))


def test_meeting_a_wish_lifts_and_missing_one_never_lowers():  # B1, C4
    a, b = _meal("A"), _meal("B")
    _run([a, b], si(wishes=_dish("bánh căn", "A")))
    assert a.score > b.score and a.parts["wish"] > 0 and b.parts["wish"] == 0.0
    assert a.wishes[0][:3] == ("dish:bánh căn", "dish", "bánh căn")


def test_meeting_two_wishes_beats_meeting_one():  # B2
    a, b = _meal("A"), _meal("B")
    w = _dish("bánh căn", "A", "B")
    w["kinds"] = [{"kind": "lẩu", "quote": "lẩu", "place_ids": ["B"]}]
    _run([a, b], si(wishes=w))
    assert b.parts["wish"] > a.parts["wish"]


def test_wish_stays_within_one():  # B3
    a = _meal("A")
    w = _dish("bánh căn", "A")
    w["kinds"] = [{"kind": "lẩu", "quote": "lẩu", "place_ids": ["A"]}]
    _run([a], si(wishes=w, vibes=[{"phrase": "ấm", "places": ["A"]}], liked_groups=["meal"],
                 context={"purpose": "food_culture"}))
    assert 0 < a.parts["wish"] <= 1


def test_a_dish_lifts_any_place_that_lists_it_whatever_its_role():  # B4 (user ruling 2026-10-15: option b)
    c = Cand(srec("C", group="cafe", usable=("experience",)), "experience")
    z = Cand(srec("Z", group="cafe", usable=("experience",)), "experience")
    _run([c, z], si(wishes=_dish("cà phê muối", "C")))
    assert c.parts["wish"] > 0 and z.parts["wish"] == 0.0


def test_a_said_wish_lifts_more_than_a_purpose():  # B5
    a = _meal("A")
    c = Cand(srec("C", group="cafe", usable=("experience",)), "experience")
    _run([a, c], si(wishes=_dish("bánh căn", "A"), context={"purpose": "relax"}))
    assert a.parts["wish"] > c.parts["wish"] > 0


def test_vibe_keeps_its_order_and_lifts_over_equal_places():  # B6
    cs = [Cand(srec(p, group="cafe", usable=("experience",)), "experience") for p in ("V1", "V2", "V3", "Z")]
    _run(cs, si(vibes=[{"phrase": "mây", "places": ["V3", "V1", "V2"]}]))
    assert [c.id for c in sorted(cs, key=lambda c: (-c.score, c.id))] == ["V3", "V1", "V2", "Z"]


def test_parts_have_wish_not_vibe_and_score_is_their_weighted_sum():  # B7
    a = _meal("A")
    _run([a], si(wishes=_dish("bánh căn", "A")))
    assert "wish" in a.parts and "vibe" not in a.parts
    assert a.score == round(sum(CFG.weights.get(k, 0.0) * v for k, v in a.parts.items()), 4)


def test_no_wishes_means_zero_wish_everywhere():  # A14, E10, Review Focus 3
    cs = [_meal("A"), Cand(srec("C"), "experience")]
    _run(cs, si())
    assert all(c.parts["wish"] == 0.0 and c.wishes == [] for c in cs)
