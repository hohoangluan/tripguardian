"""Spec §8 "Sau reorder": the user's order is kept; a shorter order of the same places is only hinted
(view["better_order"]), never applied, and keep_my_order(day) silences the hint for that day."""

import pytest
from plan_fixtures import CENTRE, SOUTH, CFG, FakeLive, decision, fake_matrix, no_geocode, spot

from planning import Engine
from planning.session import ActionError, Store


def eng(recs):
    return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                  sun_fn=lambda *a: (360, 1050), background=False)


def setup():
    # short visits: the four places fit one day, so the plan opens with nothing to choose
    recs = [spot(pid, at, i, visit=(20, 30, 45)) for pid, at, i in
            (("c1", CENTRE, 0), ("s1", SOUTH, 0), ("c2", CENTRE, 1), ("s2", SOUTH, 1))]
    d = decision([r["id"] for r in recs], days=1, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    return recs, d


def visits(view, day=0):
    return [i["place_id"] for i in view["itinerary"][day]["items"] if i["kind"] == "visit"]


def test_reorder_keeps_the_user_order_and_offers_a_shorter_one():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    zigzag = ["c1", "s1", "c2", "s2"]
    view = e.act(sid, {"type": "reorder", "day": 0, "order": zigzag})["view"]
    assert visits(view) == zigzag
    hint = view["better_order"]
    assert hint and hint[0]["day"] == 0 and hint[0]["saved_min"] >= CFG.realistic["better_order_min"]
    assert sorted(hint[0]["order"]) == sorted(zigzag) and hint[0]["order"] != zigzag
    assert isinstance(hint[0]["fixes"], list)
    # the hint is never applied: reading the session again shows the same user order and the same hint
    again = e.load(sid)["view"]
    assert visits(again) == zigzag and again["better_order"] == hint


def test_a_fine_reorder_gets_no_hint_and_keep_my_order_silences_it():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    view = e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "c2", "s1", "s2"]})["view"]
    assert not view["better_order"]
    e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "s1", "c2", "s2"]})
    out = e.act(sid, {"type": "keep_my_order", "day": 0})
    view = out["view"]
    assert not view["better_order"]
    assert visits(view) == ["c1", "s1", "c2", "s2"]
    assert out["diff"]["scope"] == "none"


def test_no_hint_before_any_reorder():
    recs, d = setup()
    e = eng(recs)
    view = e.create(d)["view"]
    assert view["better_order"] == []


def test_keep_my_order_rejects_a_bad_day_and_undo_brings_the_hint_back():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "s1", "c2", "s2"]})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "keep_my_order", "day": 5})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "keep_my_order", "day": "0"})
    assert not e.act(sid, {"type": "keep_my_order", "day": 0})["view"]["better_order"]
    assert e.act(sid, {"type": "undo"})["view"]["better_order"]


def test_taking_the_hint_is_a_plain_reorder_and_clears_it():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    hint = e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "s1", "c2", "s2"]})["view"]["better_order"][0]
    view = e.act(sid, {"type": "reorder", "day": 0, "order": hint["order"]})["view"]
    assert visits(view) == hint["order"]
    assert not view["better_order"]


def test_the_bad_realistic_reorder_gets_a_hint():
    from realistic_cases import CASES, SERVING, run_case
    if not SERVING.exists():
        pytest.skip("needs data/serving/places.json")
    run = run_case(next(c for c in CASES if c["id"] == "reorder_bad"))
    hint = run.view["better_order"]
    assert hint and hint[0]["day"] == 0
    want = [run.ids[n] for n in run.case["edits"][0]["order"]]
    assert [i["place_id"] for i in run.days[0]["items"] if i["kind"] == "visit" and i["place_id"] in want] == want


def test_in_the_background_the_hint_comes_with_the_suggestions():
    """Spec §8 "Tính nền": a live session works the best order out after the reorder answers, with the suggestions;
    the suggestions poll carries it and the next view shows it."""
    import time
    recs, d = setup()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
               sun_fn=lambda *a: (360, 1050), background=True)
    sid = e.create(d)["id"]
    e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "s1", "c2", "s2"]})
    deadline = time.monotonic() + 30
    polled = e.suggestions(sid)
    while polled["status"] == "pending" and time.monotonic() < deadline:
        time.sleep(0.05)
        polled = e.suggestions(sid)
    assert polled["status"] == "ready"
    assert polled["better_order"] and polled["better_order"][0]["day"] == 0
    view = e.load(sid)["view"]
    assert view["better_order"] == polled["better_order"]
    assert visits(view) == ["c1", "s1", "c2", "s2"]
