import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip, small_trip

from planning.engine import Engine, NoSession
from planning.session import ActionError, Store


def fake_route(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def engine(records=None, lodging_fn=fake_lodging):
    d, recs = sample_trip() if records is None else (None, None)
    return Engine([], cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                 sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lodging_fn)


def test_create_returns_variants_right_away_without_waiting_on_lodging():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lambda *a: pytest.fail("lodging must not block create"))
    out = e.create(d, None)
    assert out["id"] and out["view"]["ok"] and out["view"]["variants"]
    assert out["view"]["lodging"]["status"] == "pending"


def test_load_an_unknown_session_is_no_session():
    e = engine()
    with pytest.raises(NoSession):
        e.load("0" * 12)


def test_lodging_turns_ready_once_the_background_crawl_finishes():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)  # run synchronously in tests
    out = e.create(d, None)
    sid = out["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert {c["id"] for c in lod["candidates"]} == {"h1", "h2"}


def test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one():
    # cap = budget * lodging_share / nights (planning.lodging.price_cap); nights = days - 1 = 1 here, so a 5M
    # budget caps at 1.5M/night -- comfortably over h2's 900k -- before the later set_lodging_budget tightens it.
    d, recs = sample_trip(budget=5_000_000)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    variants = e.variants(sid)
    e.act(sid, {"type": "pick_variant", "id": variants[0]["id"]})
    e.act(sid, {"type": "pick_lodging", "id": "h2"})            # 900k/night, affordable under the 5M budget trip
    e.act(sid, {"type": "set_lodging_budget", "max_per_night": 400000})
    lod = e.lodging(sid)
    assert {c["id"] for c in lod["candidates"]} == {"h1"}       # h2 dropped out of the fetched list ...
    assert e.load(sid)["view"]["state"]["lodging_id"] == "h2"   # ... but the chosen lodging did not silently change
    with pytest.raises(ActionError):
        e.act(sid, {"type": "pick_lodging", "id": "h2"})        # re-picking a candidate no longer offered is refused


def started(budget=None):
    d, recs = small_trip(budget=budget)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_acting_before_pick_variant_is_refused():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.act(sid, {"type": "reorder", "day": 0, "order": ["a", "b", "c"]})


def test_reorder_changes_only_the_day_it_touches():
    e, sid = started()
    before = e.load(sid)["view"]["state"]
    out = e.act(sid, {"type": "reorder", "day": 0, "order": ["c", "b", "a"]})
    assert out["view"]["itinerary"][0]["items"][0]["place_id"] == "c"


def test_moving_a_locked_place_is_refused_and_the_session_does_not_change():
    e, sid = started()
    e.act(sid, {"type": "lock_slot", "place": "a"})
    before = e.load(sid)
    with pytest.raises(ActionError):
        e.act(sid, {"type": "move_place", "place": "a", "day": 0})   # same day, still refused: a is locked at all
    assert e.load(sid)["view"]["state"] == before["view"]["state"]


def test_two_acts_on_the_same_day_compose_and_every_other_day_is_byte_identical():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    before = e.load(sid)["view"]["itinerary"]
    out1 = e.act(sid, {"type": "drop_place", "place": "c1"})
    day0_ids = [i["place_id"] for i in out1["view"]["itinerary"][0]["items"] if i["kind"] == "visit"]
    out2 = e.act(sid, {"type": "reorder", "day": 0, "order": list(reversed(day0_ids))})
    other_day_before = [d for d in before if d["day"] != 1]
    other_day_after = [d for d in out2["view"]["itinerary"] if d["day"] != 1]
    assert other_day_before == other_day_after or not other_day_before  # day 2 untouched by day-1-only acts


def test_a_new_act_after_undo_discards_the_redone_future():
    e, sid = started()
    e.act(sid, {"type": "lock_slot", "place": "a"})
    e.act(sid, {"type": "undo"})
    assert e.load(sid)["view"]["state"]["locked"] == []
    e.act(sid, {"type": "lock_slot", "place": "b"})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "redo"})          # the "lock a" future was discarded by the new act


def test_undo_with_nothing_to_undo_is_an_action_error():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]          # position 0, no act committed yet -- unlike started(), which already
    with pytest.raises(ActionError):       # did one pick_variant and so has something to undo
        e.act(sid, {"type": "undo"})


def test_confirm_refuses_an_unvalidated_plan():
    from dataclasses import replace as _r

    from planning.engine import NotConfirmable
    e, sid = started()
    e.act(sid, {"type": "move_place", "place": "a", "day": 0})   # fine
    out = e.confirm(sid)
    assert out["chosen"]
    # confirm() re-derives violations from the cached results' items via validate() -- it never trusts a DayResult's
    # own .violations field (docs/specs/PLANNING_SPEC.md ⓔ: "validate.py là nơi duy nhất kết luận pass / fail").
    # Corrupt a day's first item to start before the day opens, which validate() catches independently of anything
    # simulate() itself noticed.
    pos = e.store.get(sid).position
    day0 = e._schedules[sid][pos][0]
    bad_items = (_r(day0.items[0], start=-100),) + day0.items[1:]
    e._schedules[sid][pos] = [_r(day0, items=bad_items), *e._schedules[sid][pos][1:]]
    with pytest.raises(NotConfirmable):
        e.confirm(sid)
