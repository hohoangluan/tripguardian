"""Wishes from Trip Understanding as place lifts (spec 2026-10-15-place-decision-needs-design.md §4.1, §12.1 A)."""

import pytest

from fixtures import feat, si, srec

from decision.settings import default
from decision.wishes import SAID, build, lift, strength

CFG = default()
A = CFG.wish["a"]
KIND = ("scenic_view", "photo_spot", "cozy_decor", "live_music")  # experience features that make a signature


def wishes(dishes=(), kinds=(), like=()):
    return {"dishes": list(dishes), "kinds": list(kinds), "like": list(like)}


def dish(name, *ids):
    return {"dish": name, "quote": name, "place_ids": list(ids)}


def kind(name, *ids):
    return {"kind": name, "quote": name, "place_ids": list(ids)}


def cafe(pid, feats=KIND, **kw):
    return srec(pid, group="cafe", usable=("experience",), features={f: feat("present", n=5) for f in feats}, **kw)


def test_dish_ranks_its_places_and_lifts_every_place_that_lists_it():  # A1: a café with cà phê muối counts too
    ws = build(si(wishes=wishes(dishes=[dish("bánh căn", "P1", "P2", "P3")])), [], CFG)
    assert [w.key for w in ws] == ["dish:bánh căn"]
    assert dict(ws[0].places) == {"P1": 1.0, "P2": 0.75, "P3": 0.5} and ws[0].role is None
    assert lift(ws, "P1", "meal", "meal")[0] == pytest.approx(A["dish"])
    assert lift(ws, "P1", "experience", "chill")[0] == pytest.approx(A["dish"])
    assert lift(ws, "P9", "meal", "meal")[0] == 0.0


def test_dish_without_places_gives_no_wish():  # A2
    assert build(si(wishes=wishes(dishes=[dish("halal")])), [], CFG) == ()


def test_same_wish_twice_counts_once():  # A3
    ws = build(si(wishes=wishes(dishes=[dish("Bánh căn", "P1"), dish("bánh căn", "P2")])), [], CFG)
    assert len(ws) == 1


def test_kind_lifts_its_places_fully():  # A4
    ws = build(si(wishes=wishes(kinds=[kind("karaoke", "K1", "K2")])), [], CFG)
    assert dict(ws[0].places) == {"K1": 1.0, "K2": 1.0} and ws[0].role is None


def test_vibe_ranks_like_vibe_fit():  # A5
    ws = build(si(vibes=[{"phrase": "mây", "places": ["V1", "V2", "V3", "V4"]}]), [], CFG)
    p = ws[0].places
    assert p["V1"] == 1.0 and p["V4"] == 0.5 and p["V1"] > p["V2"] > p["V3"] > p["V4"]
    assert ws[0].label == "mây"


def test_vibe_duplicates_count_once():  # Review Focus 2
    ws = build(si(vibes=[{"phrase": "mây", "places": ["V1", "V1", "V2"]}]), [], CFG)
    assert dict(ws[0].places) == {"V1": 1.0, "V2": 0.5}


def test_like_lifts_similar_places_of_the_same_kind_but_not_the_reference():  # A6
    rows = [cafe("X"), cafe("Y"), cafe("Z", feats=("hiking", "camping", "animals")),
            srec("R", group="restaurant", usable=("meal",), features={f: feat("present", n=5) for f in KIND})]
    ws = build(si(wishes=wishes(like=[{"place_id": "X", "but": [], "quote": "giống X"}])), rows, CFG,
               name=lambda pid: "Mọt Cafe" if pid == "X" else None)
    assert [w.key for w in ws] == ["like:X"] and ws[0].label == "Mọt Cafe"
    assert set(ws[0].places) == {"Y"} and ws[0].places["Y"] == 1.0


def test_like_reference_with_too_few_features_matches_nothing():  # A7
    rows = [cafe("X", feats=("scenic_view",)), cafe("Y")]
    assert build(si(wishes=wishes(like=[{"place_id": "X", "but": [], "quote": "giống X"}])), rows, CFG) == ()


def test_like_reference_missing_or_stay_gives_no_wish():  # A8, Review Focus 1
    rows = [cafe("Y"), srec("S", group="stay", usable=(), features={f: feat("present", n=5) for f in KIND})]
    for ref in ("GHOST", "S"):
        assert build(si(wishes=wishes(like=[{"place_id": ref, "but": [], "quote": "giống"}])), rows, CFG) == ()


def test_liked_group_lifts_that_group_only():  # A9, A10
    ws = build(si(liked_groups=["chill", "meal"]), [], CFG)
    assert [w.key for w in ws] == ["group:chill", "group:meal"]
    assert strength(ws[0], "C", "experience", "chill") == 1.0
    assert strength(ws[0], "N", "experience", "nature") == 0.0
    assert strength(ws[1], "M", "meal", "meal") == 1.0


@pytest.mark.parametrize("purpose,group", [("relax", "chill"), ("food_culture", "meal"), ("nature", "nature"),
                                           ("explore", "sights")])
def test_purpose_maps_to_a_group_and_leans_less(purpose, group):  # A11
    ws = build(si(context={"purpose": purpose}), [], CFG)
    assert [(w.kind, w.group) for w in ws] == [("purpose", group)] and ws[0].a == A["purpose"] < A["dish"]


def test_purpose_photo_lifts_only_firm_photo_spots():  # A12
    def firm(fid, value):
        return {"P1"} if (fid, value) == ("photo_spot", "present") else set()
    ws = build(si(context={"purpose": "photo"}), [], CFG, firm=firm)
    assert dict(ws[0].places) == {"P1": 1.0}
    assert build(si(context={"purpose": "photo"}), [], CFG, firm=lambda f, v: set()) == ()


@pytest.mark.parametrize("purpose", ["bond", "adventure", None])
def test_unmapped_purpose_gives_no_wish(purpose):  # A13
    assert build(si(context={"purpose": purpose}), [], CFG) == ()


def test_lift_is_noisy_or_and_stays_within_one():  # B3 at the source
    ws = build(si(wishes=wishes(dishes=[dish("bánh căn", "M")], kinds=[kind("lẩu", "M")]), liked_groups=["meal"],
                  context={"purpose": "food_culture"}), [], CFG)
    value, hits = lift(ws, "M", "meal", "meal")
    one = lift(ws[:1], "M", "meal", "meal")[0]
    assert one < value <= 1.0
    assert [h[1] for h in hits][:2] == ["dish", "kind"] and all(h[1] in SAID for h in hits[:2])


def test_photos_with_the_same_phrase_each_lift_their_places():  # final review I1
    ws = build(si(vibes=[{"phrase": "ảnh bạn gửi", "places": ["A", "B"]},
                         {"phrase": "ảnh bạn gửi", "places": ["C", "D"]}]), [], CFG)
    assert [w.key for w in ws] == ["vibe:0", "vibe:1"]
    assert lift(ws, "C", "experience", "chill")[0] > 0


def test_two_like_references_with_one_name_both_count():  # final review I1
    rows = [cafe("X1"), cafe("X2"), cafe("Y")]
    ws = build(si(wishes=wishes(like=[{"place_id": "X1", "but": [], "quote": "giống"},
                                      {"place_id": "X2", "but": [], "quote": "giống"}])), rows, CFG,
               name=lambda pid: "Chuỗi cà phê")
    assert [w.key for w in ws] == ["like:X1", "like:X2"]


def test_like_reference_without_a_name_has_no_raw_id_label():  # M5
    rows = [cafe("X"), cafe("Y")]
    ws = build(si(wishes=wishes(like=[{"place_id": "X", "but": [], "quote": "giống X"}])), rows, CFG)
    assert ws[0].label == ""
