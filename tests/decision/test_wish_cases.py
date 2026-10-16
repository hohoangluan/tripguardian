"""Wish ranking on whole runs: invariants (spec §12.1 C) and user cases from the persona matrix (§12.1 E)."""

from fixtures import feat, fit_entry, hard, love, si, srec

from corpus.serving import dishes
from decision.pipeline import Data, run, why_not
from decision.session import Session, State
from decision.settings import default

CFG = default()
KIND = ("scenic_view", "photo_spot", "cozy_decor", "live_music")


def menu(rec, *names):
    rec["menu"] = {"dishes": [{"name": n, "name_en": None, "section": None, "popular": False, "price": None}
                              for n in names], "photos": []}
    return rec


def meal(pid, *names, **kw):
    return menu(srec(pid, group="restaurant", category="Nhà hàng", usable=("meal",), **kw), *names)


def cafe(pid, **kw):
    return srec(pid, group="cafe", category="Quán cà phê", usable=("experience",), **kw)


def nature(pid, **kw):
    return srec(pid, group="nature", category="Thắng cảnh", usable=("experience",), **kw)


def dish_wish(recs, *names):
    return [{"dish": n, "quote": n, "place_ids": [h["id"] for h in dishes.search(recs, n)]} for n in names]


def W(dishes_=(), kinds=(), like=()):
    return {"dishes": list(dishes_), "kinds": list(kinds), "like": list(like)}


def go(search, recs, state=None, cfg=CFG):
    return run(Session(id="0" * 12, search_input=search, state=state or State()), Data(recs), cfg)


def order(res, gid):
    return res.ranked.get(gid, [])


def every(res):
    return {pid for ids in res.ranked.values() for pid in ids}


# ---------- invariants (C) ----------

def test_wishes_reorder_but_never_add_or_remove_places():  # C3, C4, C5
    recs = [meal("M1", "bánh căn"), meal("M2"), cafe("C1"), cafe("C2"), nature("N1"), nature("N2")]
    plain = go(si(), recs)
    wished = go(si(wishes=W(dish_wish(recs, "bánh căn"), [{"kind": "cà phê", "quote": "cà phê", "place_ids": ["C2"]}]),
                   liked_groups=["chill"], context={"purpose": "relax"}), recs)
    assert every(plain) == every(wished)
    assert set(order(plain, "nature")) == set(order(wished, "nature"))
    assert order(wished, "chill")[0] == "C2"
    assert all(wished.cands[p].parts["wish"] >= 0 for p in every(wished))


def test_a_wished_place_that_fails_a_hard_filter_never_shows():  # C1
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    recs[0]["service"]["vegetarian_options"] = feat("no", n=5)
    recs[1]["service"]["vegetarian_options"] = feat("yes", n=5)
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq")], wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert "M1" not in every(res) and order(res, "meal") == ["M2"]


def test_unknown_evidence_goes_to_unverified_not_the_list():  # C2
    recs = [meal("M1", "bánh căn")]
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq", policy="flag")],
                wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert "M1" not in every(res) and [c["id"] for c in res.view["unverified"]["cards"]] == ["M1"]


def test_anchor_and_chosen_places_keep_their_place():  # C6, C7
    recs = [meal("M1", "bánh căn"), meal("M2"), nature("N1"), nature("N2")]
    st = State(selected=["N2"])
    res = go(si(anchors=[{"place_id": "N1", "priority": "must"}], wishes=W(dish_wish(recs, "bánh căn")),
                liked_groups=["meal"]), recs, st)
    assert res.view["groups"][0]["id"] == "anchors" and res.view["groups"][0]["cards"][0]["id"] == "N1"
    assert order(res, "nature")[0] == "N2"


def test_novelty_new_keeps_a_visited_place_out_even_if_wished():  # C8, E15
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    res = go(si(novelty={"level": "new", "visited": ["M1"]}, wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert order(res, "meal") == ["M2"]


def test_stays_and_unknown_ids_in_a_wish_are_ignored():  # C9, C10
    recs = [cafe("C1"), srec("S1", group="stay", category="Khách sạn", usable=())]
    res = go(si(wishes=W(kinds=[{"kind": "view", "quote": "view", "place_ids": ["S1", "GHOST", "C1"]}])), recs)
    assert "S1" not in every(res) and "GHOST" not in res.view["shortlist"] and order(res, "chill") == ["C1"]


# ---------- user cases (E) ----------

def test_food_tour_place_with_both_dishes_first():  # E1
    recs = [meal("M1"), meal("M2", "bánh căn"), meal("M3", "bánh căn", "lẩu gà lá é")]  # ids against the wished order
    res = go(si(wishes=W(dish_wish(recs, "lẩu gà lá é", "bánh căn")), context={"purpose": "food_culture"}), recs)
    assert order(res, "meal") == ["M3", "M2", "M1"]


def test_couple_chill_quiet_cafe_first_nature_untouched():  # E2
    recs = [cafe("C1", features={"crowd": feat("high", n=5)}), cafe("C2", features={"crowd": feat("low", n=5)}),
            nature("N1"), nature("N2")]
    res = go(si(liked_groups=["chill"], soft_weights=[love("crowd", "low")], context={"companions": ["partner"]}), recs)
    assert order(res, "chill")[0] == "C2" and set(order(res, "nature")) == {"N1", "N2"}


def test_family_with_kids_fit_and_kind_beat_kind_only():  # E3
    good = {"fit": {"kids": fit_entry("good")}}
    recs = [srec("K1", group="amusement"), srec("K2", group="amusement"),
            srec("K3", group="amusement", features={"kids_play_area": feat("present", n=5)}, details=good)]
    res = go(si(context={"companions": ["kids"]}, soft_weights=[love("kids_play_area")],
                wishes=W(kinds=[{"kind": "khu vui chơi", "quote": "khu vui chơi", "place_ids": ["K3", "K2"]}])), recs)
    assert order(res, "sights") == ["K3", "K2", "K1"]


def test_wheelchair_photo_place_that_is_bad_for_wheelchairs_never_shows():  # E4
    recs = [nature("P1", features={"photo_spot": feat("present", n=5)}, details={"fit": {"wheelchair": fit_entry("bad")}}),
            nature("P2", features={"photo_spot": feat("present", n=5)}, details={"fit": {"wheelchair": fit_entry("good")}})]
    res = go(si(hard_filters=[hard("fit.wheelchair", "bad")], context={"purpose": "photo"}), recs)
    assert "P1" not in every(res) and order(res, "nature") == ["P2"]


def test_vegetarian_group_wished_dish_unverified_stays_out():  # E5
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    recs[1]["service"]["vegetarian_options"] = feat("yes", n=5)
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq")], wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert order(res, "meal") == ["M2"] and "M1" not in every(res)


def test_like_x_but_quieter():  # E6
    f = lambda crowd: {**{k: feat("present", n=5) for k in KIND}, "crowd": feat(crowd, n=5)}
    recs = [cafe("X", features=f("high")), cafe("Z", features=f("high")), cafe("Y", features=f("low")),
            cafe("W", features={**{k: feat("present", n=5) for k in ("hiking", "camping", "animals")},
                                "crowd": feat("high", n=5)})]
    res = go(si(wishes=W(like=[{"place_id": "X", "but": ["crowd=low"], "quote": "giống X nhưng vắng hơn"}]),
                soft_weights=[love("crowd", "low")]), recs)
    chill = order(res, "chill")
    assert chill.index("Y") < chill.index("Z") < chill.index("W")
    assert "X" in chill and res.cands["X"].parts["wish"] == 0.0


def test_cloud_hunting_look_keeps_its_order():  # E7
    recs = [nature(p) for p in ("V1", "V2", "V3", "Z")]
    res = go(si(vibes=[{"phrase": "sương sáng sớm", "places": ["V3", "V1", "V2"]}]), recs)
    assert order(res, "nature") == ["V3", "V1", "V2", "Z"]


def test_nightlife_bar_is_not_banned_by_no_alcohol_and_karaoke_leads():  # E8
    recs = [srec("B1", group="bar", category="Quán bar", usable=("experience",)),
            srec("K0", group="other", category="Quán nhậu", usable=("experience",)),
            srec("K1", group="other", category="Karaoke", usable=("experience",))]
    res = go(si(hard_filters=[hard("activity", "alcohol_consumption")],
                wishes=W(kinds=[{"kind": "karaoke", "quote": "karaoke", "place_ids": ["K1"]},
                                {"kind": "bar", "quote": "bar", "place_ids": ["B1"]}])), recs)
    assert "B1" in order(res, "chill") and order(res, "sights")[0] == "K1"


def test_mixed_group_both_wished_groups_lead():  # E9
    recs = [meal("M1"), meal("M2", "bánh căn"), nature("N1"), nature("N2"), cafe("C1")]
    res = go(si(context={"companions": ["kids", "parents"]}, wishes=W(dish_wish(recs, "bánh căn")),
                liked_groups=["nature", "meal"]), recs)
    assert order(res, "meal")[0] == "M2" and order(res, "nature") and order(res, "chill") == ["C1"]


def test_change_of_mind_keeps_the_chosen_place():  # E11
    recs = [meal("M1", "bánh căn"), meal("M2"), meal("M3")]
    first = go(si(wishes=W(dish_wish(recs, "bánh căn"))), recs, State(selected=["M2"]))
    st = State(selected=["M2"], shown=first.shown)
    second = go(si(wishes=W(kinds=[{"kind": "lẩu", "quote": "lẩu", "place_ids": ["M3"]}])), recs, st)
    assert order(second, "meal")[:2] == ["M2", "M3"]


def test_dish_no_corpus_place_has_changes_nothing():  # E12
    recs = [meal("M1"), meal("M2")]
    assert order(go(si(wishes=W([{"dish": "halal", "quote": "halal", "place_ids": []}])), recs), "meal") == \
        order(go(si(), recs), "meal")


def test_more_wishes_than_slots_keeps_everyone_and_orders_by_wishes_met():  # E13
    recs = [meal(f"M{i}", *(["a", "b"] if i == 9 else ["a"] if i == 8 else [])) for i in range(10)]
    res = go(si(context={"days": 1}, wishes=W(dish_wish(recs, "a", "b", "c", "d", "e"),
                                              [{"kind": f"k{j}", "quote": f"k{j}", "place_ids": []} for j in range(3)])), recs)
    assert order(res, "meal")[:2] == ["M9", "M8"] and len(order(res, "meal")) == 10


def test_coach_party_hard_access_runs_before_the_wish():  # E14
    recs = [meal("R1"), meal("R2")]
    recs[0]["effort"]["coach_access"] = feat("no", n=5)
    recs[1]["effort"]["coach_access"] = feat("yes", n=5)
    res = go(si(context={"people": 18, "mobility": "car"}, hard_filters=[hard("coach_access", "no")],
                wishes=W(kinds=[{"kind": "nhà hàng", "quote": "nhà hàng", "place_ids": ["R1", "R2"]}])), recs)
    assert order(res, "meal") == ["R2"]
