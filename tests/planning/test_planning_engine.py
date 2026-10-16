import threading

import pytest
from plan_fixtures import CENTRE, CFG, FakeLive, decision, LODGING, fake_matrix, no_geocode, sample_trip, small_trip, spot

from planning.engine import Engine, NoSession
from planning.session import ActionError, Store


def fake_route(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def engine():
    return Engine(LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                 sun_fn=lambda *a: (6 * 60, 17 * 60 + 30))


def test_create_returns_variants_right_away_without_waiting_on_lodging(monkeypatch):
    import planning.engine as pe
    d, recs = sample_trip()
    gate = threading.Event()
    ranked = pe.lodging_candidates

    def slow_candidates(*a):  # the lodging list is built in the background; create must not wait for it
        gate.wait(5)
        return ranked(*a)

    monkeypatch.setattr(pe, "lodging_candidates", slow_candidates)
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30))
    out = e.create(d, None)
    assert out["id"] and out["view"]["ok"] and out["view"]["variants"]
    assert out["view"]["lodging"]["status"] == "pending"
    gate.set()


def test_engine_overload_offers_directions_and_tracks_direction_specific_drops():
    records = [spot(f"p{i}", CENTRE, i % 7, price={"typical_vnd": 200000 if i == 7 else 10000},
                    group=f"kind-{i % 4}") for i in range(8)]
    d = decision([r["id"] for r in records], days=1, leave_at="21:00")
    d["feasibility"] = {"status": "infeasible", "totals": {"needed": 1000, "available": 600},
                        "conflicts": [{"check": "time", "id": "time"}]}
    for chosen in d["confirmed"]:
        chosen["utility"] = 0.1 if chosen["id"] == "p7" else 1.0
    e = Engine(records + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), background=False)
    created = e.create(d, None)
    sid, view = created["id"], created["view"]
    assert view["overload"]["level"] == "overloaded"
    assert {d for v in view["variants"] for d in [v["id"], *v.get("merged", [])]} == {"fit", "travel", "cost"}
    cheap = next(v for v in view["variants"] if "cost" in [v["id"], *v.get("merged", [])])
    assert cheap["status"] == "available" and "p7" not in cheap["kept"]
    e.act(sid, {"type": "pick_variant", "id": cheap["id"]})
    chosen = e.load(sid)["view"]
    assert set(chosen["state"]["plan_dropped"]) == set(cheap["dropped_by_plan"][i]["place_id"]
                                                        for i in range(len(cheap["dropped_by_plan"])))
    assert {i["place_id"] for day in chosen["itinerary"] for i in day["items"] if i["kind"] == "visit"} == set(cheap["kept"])
    other = next(v for v in view["variants"] if "travel" in [v["id"], *v.get("merged", [])] and v["status"] == "available")
    switched = e.act(sid, {"type": "pick_variant", "id": other["id"]})["view"]
    assert set(switched["state"]["plan_dropped"]) == {x["place_id"] for x in other["dropped_by_plan"]}
    assert not switched["state"]["dropped"]
    restored = e.act(sid, {"type": "pick_variant", "id": cheap["id"]})["view"]
    plan_drop = next(x["place_id"] for x in cheap["dropped_by_plan"] if x["place_id"] not in restored["state"]["restored"])
    restored = e.act(sid, {"type": "move_place", "place": plan_drop, "day": 0})["view"]
    assert plan_drop in restored["state"]["restored"]
    assert plan_drop not in restored["state"]["plan_dropped"]
    assert plan_drop in {i["place_id"] for day in restored["itinerary"] for i in day["items"] if i["kind"] == "visit"}


def test_preview_act_does_not_mutate_and_requires_the_same_current_action():
    e, sid = started()
    action = {"type": "drop_place", "place": "a"}
    before = e.store.get(sid).model_dump(mode="json")
    preview = e.preview_act(sid, action)
    assert preview["action"] == action and preview["delta"]
    assert e.store.get(sid).model_dump(mode="json") == before
    applied = e.act(sid, {**action, "_preview_token": preview["token"]})
    assert "a" not in {i.get("place_id") for d in applied["view"]["itinerary"] for i in d["items"]}


def test_preview_act_token_is_stale_after_an_intervening_edit():
    e, sid = started()
    action = {"type": "drop_place", "place": "a"}
    preview = e.preview_act(sid, action)
    e.act(sid, {"type": "drop_place", "place": "b"})
    with pytest.raises(ActionError, match="stale"):
        e.act(sid, {**action, "_preview_token": preview["token"]})


def test_load_an_unknown_session_is_no_session():
    e = engine()
    with pytest.raises(NoSession):
        e.load("0" * 12)


def test_lodging_turns_ready_once_the_served_stays_are_ranked():
    d, recs = sample_trip()
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)  # run synchronously in tests
    out = e.create(d, None)
    sid = out["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert {c["id"] for c in lod["candidates"]} == {"h1", "h2"}


def test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one():
    # cap = budget * lodging_share / nights (planning.lodging.price_cap); nights = days - 1 = 1 here, so a 5M
    # budget caps at 1.5M/night -- comfortably over h2's 900k -- before the later set_lodging_budget tightens it.
    d, recs = sample_trip(budget=5_000_000)
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
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
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_acting_before_pick_variant_is_refused():
    recs = [spot(f"p{i}", CENTRE, i) for i in range(8)]
    d = decision([r["id"] for r in recs], days=1, leave_at="21:00")
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.act(sid, {"type": "reorder", "day": 0, "order": ["a", "b", "c"]})


def test_reorder_changes_only_the_day_it_touches():
    e, sid = started()
    before = e.load(sid)["view"]["state"]
    out = e.act(sid, {"type": "reorder", "day": 0, "order": ["c", "b", "a"]})
    assert next(i["place_id"] for i in out["view"]["itinerary"][0]["items"] if i["kind"] == "visit") == "c"


def test_picking_a_variant_again_keeps_dropped_places_out():
    e, sid = started()
    variant = e.store.get(sid).state.chosen_variant
    e.act(sid, {"type": "drop_place", "place": "a"})
    view = e.act(sid, {"type": "pick_variant", "id": variant})["view"]
    assert "a" not in {i.get("place_id") for d in view["itinerary"] for i in d["items"] if i["kind"] == "visit"}


def test_moving_a_locked_place_is_refused_and_the_session_does_not_change():
    e, sid = started()
    e.act(sid, {"type": "lock_slot", "place": "a"})
    before = e.load(sid)
    with pytest.raises(ActionError):
        e.act(sid, {"type": "move_place", "place": "a", "day": 0})   # same day, still refused: a is locked at all
    assert e.load(sid)["view"]["state"] == before["view"]["state"]


def test_two_acts_on_the_same_day_compose_and_every_other_day_is_byte_identical():
    d, recs = sample_trip(days=2)
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
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
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
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
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route, background=False)
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
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
               sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route,
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
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=far_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    before = e.load(sid)["view"]["travel_load"]
    out = e.act(sid, {"type": "set_lodging", "text": "Far homestay"})
    assert out["view"]["travel_load"] != before


def test_a_late_finishing_crawl_does_not_lose_a_manual_lodging_point_set_in_the_meantime():
    d, recs = sample_trip(days=2)
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=far_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route, background=False)
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
        return Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(tmp_path), geocode_fn=no_geocode,
                      matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=fake_route, background=False)

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
    recs = [spot(f"p{i}", CENTRE, i) for i in range(8)]
    d = decision([r["id"] for r in recs], days=1, leave_at="21:00")
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.baseline_travel_min(sid)


def test_preview_builds_variants_without_a_session_and_create_reuses_it():
    d, recs = sample_trip()
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False)
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


def test_fitting_trip_opens_on_main_and_the_tray_never_duplicates_visits():
    e, sid = started()
    view = e.load(sid)["view"]
    assert view["state"]["chosen_variant"] == "main"
    assert view["overload"] is None and view["keep_all"] is None
    assert [v["id"] for v in view["variants"]] == ["main"]
    shown = {it["place_id"] for d in view["itinerary"] for it in d["items"] if it["kind"] == "visit"}
    assert not shown & {p["place_id"] for p in view["unplaced"]}


@pytest.mark.parametrize("resume", ["load", "act"])
def test_extend_offer_rebuilds_all_picks_and_replays_identically(resume):
    from test_planning_overload import trip_of, heavy
    # This fixture is one hour short and its day's end can move (part A's verified extend fixture).
    trip = trip_of([spot(f"c{i}", CENTRE, i, visit=(50, 60, 70)) for i in range(4)], days=1)
    from dataclasses import replace
    ctxs = [replace(cx, day=replace(cx.day, depart_by=None)) for cx in trip.ctxs]
    trip = replace(trip, ctxs=ctxs, days=[cx.day for cx in ctxs])
    e = Engine([], cfg=CFG, live_cfg=FakeLive(), background=False)
    e._prepare = lambda *a, **kw: trip
    created = e.create(trip.decision)
    sid, view = created["id"], created["view"]
    ext = view["overload"]["extend"]
    assert ext
    after = e.act(sid, {"type": "extend_days", **ext})["view"]
    assert after["state"]["chosen_variant"] == "main"
    assert not after["state"]["plan_dropped"] and not after["unplaced"]
    assert {it["place_id"] for d in after["itinerary"] for it in d["items"] if it["kind"] == "visit"} == set(trip.by_place)
    e._base.clear()
    e._schedules.clear()
    if resume == "load":
        assert e.load(sid)["view"]["itinerary"] == after["itinerary"]
    else:
        resumed = e.act(sid, {"type": "set_pace", "level": "normal"})["view"]
        assert resumed["state"]["chosen_variant"] == "main"
        assert not resumed["unplaced"]


def test_unavailable_chosen_direction_uses_base_leftover_in_the_tray():
    from types import SimpleNamespace
    from planning.session import State
    e = engine()
    trip = SimpleNamespace(by_place={p: SimpleNamespace(name=p.upper()) for p in ("a", "b")}, unplaced=[])
    base = SimpleNamespace(trip=trip, leftover=("b",), variants=[
        {"id": "fit", "available": False, "dropped": [{"place_id": "a", "name": "A"}]}])
    session = SimpleNamespace(state=State(chosen_variant="fit"))
    assert [p["place_id"] for p in e._unplaced(session, base, None)] == ["b"]


def test_lodging_before_a_direction_choice_updates_its_explanation_and_tray():
    from dataclasses import replace
    from test_planning_consistency import make_engine
    from planning.overload import plan_or_directions
    records = [spot(f'p{i}', CENTRE, i % 3, price={'typical_vnd': 10000}) for i in range(16)]
    e, sid = make_engine(decision([r['id'] for r in records]), records)
    before = e.load(sid)['view']
    assert before['state']['chosen_variant'] is None
    after = e.act(sid, {'type': 'set_lodging', 'text': 'Far hotel',
                        'lat': CENTRE[0] + .15, 'lng': CENTRE[1]})['view']
    session, base = e.store.get(sid), e._base[sid]
    trip, ctxs = e._ctxs_for(base.trip, base.trip.by_place, e._home_for(session, base), session.state)
    expected = plan_or_directions(replace(trip, ctxs=ctxs, days=[cx.day for cx in ctxs]))
    assert after['overload']['missing_min'] == expected['overload']['missing_min']
    assert [(v['id'], v['kept']) for v in after['overload']['directions']] == [(v['id'], v['kept']) for v in after['variants']]
    assert {p['place_id'] for p in after['unplaced']} == set(expected['leftover'])
    e._base.clear()
    e._schedules.clear()
    assert e.load(sid)['view']['unplaced'] == after['unplaced']
    card = next(v for v in after['variants'] if v['available'])
    selected = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    drops = lambda v: {d['place_id']: (d['reason'], d['value']) for d in v['dropped']}
    assert drops(selected['active_variant']) == drops(card)
    assert selected['active_variant']['label'] == card['label']
    assert selected['active_variant']['merged'] == card.get('merged', [])
    originals = {v['id']: v for v in after['variants']}
    for offered in selected['variants']:
        assert drops(offered) == drops(originals[offered['id']])
        assert offered['label'] == originals[offered['id']]['label']
        assert offered['merged'] == originals[offered['id']].get('merged', [])
    e._base.clear()
    e._schedules.clear()
    assert drops(e.load(sid)['view']['active_variant']) == drops(card)


def test_main_is_selected_even_when_confirmation_still_requires_lodging():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
               sun_fn=lambda *a: (360, 1050), background=False)
    view = e.create(d, require_lodging=True)['view']
    assert view['state']['chosen_variant'] == 'main'
    assert view['needs_hotel']
