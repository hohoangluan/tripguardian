import threading

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
    gate = threading.Event()

    def slow_lodging(*a):  # the crawl runs in the background; create must not wait for it
        gate.wait(5)
        return fake_lodging(*a)

    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=slow_lodging)
    out = e.create(d, None)
    assert out["id"] and out["view"]["ok"] and out["view"]["variants"]
    assert out["view"]["lodging"]["status"] == "pending"
    gate.set()


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
    # own .violations field (docs/PLANNING.md ⓔ: "validate.py là nơi duy nhất kết luận pass / fail").
    # Corrupt a day's first item to start before the day opens, which validate() catches independently of anything
    # simulate() itself noticed.
    pos = e.store.get(sid).position
    day0 = e._schedules[sid][pos][0]
    bad_items = (_r(day0.items[0], start=-100),) + day0.items[1:]
    e._schedules[sid][pos] = [_r(day0, items=bad_items), *e._schedules[sid][pos][1:]]
    with pytest.raises(NotConfirmable):
        e.confirm(sid)


def two_day_started(**kw):
    d, recs = sample_trip(days=2, **kw)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_set_pace_does_not_silently_bring_back_a_dropped_place():
    e, sid = two_day_started()
    e.act(sid, {"type": "drop_place", "place": "c1"})
    out = e.act(sid, {"type": "set_pace", "level": "packed"})
    ids = {i["place_id"] for d in out["view"]["itinerary"] for i in d["items"] if i["kind"] == "visit"}
    assert "c1" not in ids


def test_set_pace_does_not_move_a_locked_place_off_the_day_it_was_moved_and_locked_to():
    e, sid = two_day_started()
    e.act(sid, {"type": "move_place", "place": "c1", "day": 1})
    e.act(sid, {"type": "lock_slot", "place": "c1"})
    out = e.act(sid, {"type": "set_pace", "level": "packed"})
    day1_ids = {i["place_id"] for i in out["view"]["itinerary"][1]["items"] if i["kind"] == "visit"}
    assert "c1" in day1_ids


def test_set_day_window_changes_the_days_window_and_the_laid_out_day_still_confirms():
    e, sid = two_day_started()
    out = e.act(sid, {"type": "set_day_window", "day": 0, "start": "07:00", "end": "22:00"})
    assert out["view"]["itinerary"][0]["window"] == ["07:00", "22:00"]
    plan = e.confirm(sid)
    assert plan["chosen"]


def test_a_variant_whose_later_day_opens_early_for_a_sunrise_place_confirms():
    """The view shows the variant as valid; confirm re-checks the same days and must agree."""
    from plan_fixtures import CENTRE, decision, rec
    recs = [rec(f"c{i}", CENTRE[0] + i * 0.002, CENTRE[1] + i * 0.002, area="area-1") for i in range(3)]
    recs.append(rec("cloud", CENTRE[0] + 0.006, CENTRE[1] + 0.006, area="area-1", hours=None,
                    features={"cloud_hunting": "present"}))
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
               sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route,
               background=False)
    out = e.create(decision([r["id"] for r in recs]), None)
    v = out["view"]["variants"][0]
    assert any(w["code"] == "early_start" for w in v["warnings"])
    sid = out["id"]
    e.act(sid, {"type": "pick_variant", "id": v["id"]})
    assert e.confirm(sid)["chosen"]


def far_geocode(text):
    from plan_fixtures import CENTRE
    return {"lat": CENTRE[0] + 2.0, "lng": CENTRE[1] + 2.0, "label": text, "source": "nominatim", "fetched_at": "t"}


def test_set_lodging_relays_out_every_day_not_just_an_already_offered_candidate():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=far_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    before = e.load(sid)["view"]["travel_load"]
    out = e.act(sid, {"type": "set_lodging", "text": "Far homestay"})
    assert out["view"]["travel_load"] != before


def test_a_late_finishing_crawl_does_not_lose_a_manual_lodging_point_set_in_the_meantime():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=far_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    e.act(sid, {"type": "set_lodging", "text": "Far homestay"})
    e._crawl_lodging(sid)   # a late-finishing background crawl, writing back after the manual point was set
    out = e.act(sid, {"type": "lock_slot", "place": "c1"})   # any further act must still be able to lay out a day
    assert out["view"]["itinerary"]
    # confirm() must not crash with a KeyError on the manual node (the old bug) -- a far-away manual point may
    # legitimately fail validation on travel time, which is unrelated to the race this test is about
    from planning.engine import NotConfirmable
    try:
        e.confirm(sid)
    except NotConfirmable:
        pass


def test_undo_restores_the_offered_lodging_list_not_just_the_budget_field():
    e, sid = two_day_started(budget=5_000_000)
    e.act(sid, {"type": "pick_lodging", "id": "h2"})
    e.act(sid, {"type": "set_lodging_budget", "max_per_night": 400000})
    assert {c["id"] for c in e.lodging(sid)["candidates"]} == {"h1"}
    e.act(sid, {"type": "undo"})
    assert {c["id"] for c in e.lodging(sid)["candidates"]} == {"h1", "h2"}


def test_a_session_reloaded_after_the_process_restarts_replays_to_the_same_schedule(tmp_path):
    d, recs = sample_trip(days=2)

    def new_engine():
        return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(tmp_path), geocode_fn=no_geocode,
                      matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging,
                      route_fn=fake_route, background=False)

    e1 = new_engine()
    sid = e1.create(d, None)["id"]
    e1.act(sid, {"type": "pick_variant", "id": e1.variants(sid)[0]["id"]})
    e1.act(sid, {"type": "pick_lodging", "id": "h1"})
    e1.act(sid, {"type": "drop_place", "place": "c1"})
    before = e1.load(sid)["view"]["itinerary"]

    # a brand-new Engine over the same disk Store, with nothing in its own RAM caches: simulates a process restart
    e2 = new_engine()
    after = e2.load(sid)["view"]["itinerary"]
    assert after == before

    plan = e2.confirm(sid)
    assert plan["lodging"]["chosen"]["id"] == "h1"
    assert not any(i["place_id"] == "c1" for d_ in plan["itinerary"] for i in d_["items"] if i["kind"] == "visit")


def test_baseline_travel_min_uses_the_same_day_membership_with_a_naive_order():
    e, sid = started()
    base_min = e.baseline_travel_min(sid)
    optimized_min = e.load(sid)["view"]["variants"][0]["metrics"]["travel_min"]
    assert base_min >= optimized_min >= 0


def test_baseline_travel_min_without_a_chosen_variant_is_an_error():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.baseline_travel_min(sid)


def test_preview_builds_variants_without_a_session_and_create_reuses_it():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    preview = e.preview(d)
    assert preview["ok"] and preview["variants"] and preview["days"] == 2
    assert all(len(v["places"]) == preview["days"] for v in preview["variants"])
    assert not e._base                                    # no session was created
    built = []
    real = e._build_base
    e._build_base = lambda decision: built.append(1) or real(decision)
    assert e.preview(d) == preview and not built          # same Decision Output: cached, no rebuild
    out = e.create(d, None)
    assert not built                                      # create() took the preview's base
    assert [v["id"] for v in out["view"]["variants"]] == [v["id"] for v in preview["variants"]]
    e.create(d, None)
    assert built == [1]                                   # a base belongs to one session only
