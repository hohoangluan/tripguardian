import threading
from dataclasses import replace

import pytest
from plan_fixtures import CFG, FakeLive, day_ctx, decision, fake_matrix, no_geocode, rec

from planning.engine import Engine
from planning.session import Store


def started(days=2, background=False):
    records = [rec("a", 11.94, 108.45, price={"typical_vnd": 50000}),
               rec("b", 11.941, 108.45),
               rec("cafe", 11.942, 108.45, group="cafe", usable=("meal", "experience", "backup"),
                   price={"typical_vnd": 100000})]
    d = decision(["a", "b"], days=days)
    d["backup_pool"] = [{"id": "cafe", "for": "a"}]
    d["trip_context"]["activities"] = {"cafe": "coffee"}
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), matrix_fn=fake_matrix,
               geocode_fn=no_geocode, sun_fn=lambda *a: None, lodging_fn=lambda *a: [],
               route_fn=lambda *a: None, background=background)
    sid = e.create(d)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_current_metrics_keep_unknown_prices_and_replay():
    e, sid = started()
    view = e.act(sid, {"type": "add_from_backup", "place": "cafe", "day": 0})["view"]
    assert view["metrics"]["cost_vnd"] == 150000
    assert view["metrics"]["cost_unknown"] == 1
    e.act(sid, {"type": "drop_place", "place": "a"})
    view = e.act(sid, {"type": "set_pace", "level": "slow"})["view"]
    assert view["metrics"]["cost_vnd"] == 100000
    e._base.clear()
    e._schedules.clear()
    assert e.load(sid)["view"]["metrics"] == view["metrics"]


def test_proposal_can_move_a_current_backup():
    e, sid = started()
    e.act(sid, {"type": "add_from_backup", "place": "cafe", "day": 0})
    s = e.store.get(sid)
    state, results = e._proposal_trial(e._base[sid], s, s.state, e._turn_current(s, e._base[sid]),
                                     {"variant_id": s.state.chosen_variant,
                                      "acts": [{"type": "move_place", "place": "cafe", "day": 1}]})
    assert "cafe" in results[1].order
    assert state.activity_override["cafe"] == "coffee"


def test_render_failure_does_not_commit_an_edit(monkeypatch):
    e, sid = started()
    before = e.store.get(sid).model_dump()
    with monkeypatch.context() as patch:
        patch.setattr(e, "_view", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("render failed")))
        with pytest.raises(RuntimeError, match="render failed"):
            e.act(sid, {"type": "drop_place", "place": "a"})
    assert e.store.get(sid).model_dump() == before
    assert e.load(sid)["view"]["itinerary"]


def test_local_insertion_uses_linear_simulations_and_drop_keeps_order(monkeypatch):
    import planning.repair as repair
    cx = day_ctx([rec(pid, 11.94, 108.45) for pid in ("a", "b", "c", "d")])
    calls = []
    original = repair.simulate
    def counted(order, ctx):
        calls.append(tuple(order))
        return original(order, ctx)
    monkeypatch.setattr(repair, "simulate", counted)
    result = repair.repair_day(["a", "b", "c", "d"], cx, ("c", "b", "a"), set(), CFG)
    assert not result.violations
    assert len(calls) <= 4
    assert [p for p in result.order if p != "d"] == ["c", "b", "a"]
    calls.clear()
    result = repair.repair_day(["c", "a"], cx, ("c", "b", "a"), set(), CFG)
    assert result.order == ("c", "a") and len(calls) == 1


def test_suggestions_do_not_block_edits_or_repeat_on_load(monkeypatch):
    import planning.engine as module
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def blocked(*args):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        finished.set()
        return []
    monkeypatch.setattr(module, "recommend", blocked)
    try:
        e, sid = started(background=True)
        assert entered.wait(2)
        view = e.load(sid)["view"]
        assert view["suggestions"]["status"] == "pending"
        assert view["metrics"]["cost_vnd"] == 50000
        for _ in range(3):
            assert e.load(sid)["view"]["suggestions"]["token"] == view["suggestions"]["token"]
        assert len(calls) == 1
        edited = e.act(sid, {"type": "drop_place", "place": "b"})["view"]
        assert edited["suggestions"]["token"] != view["suggestions"]["token"]
        undone = e.act(sid, {"type": "undo"})["view"]
        assert undone["suggestions"]["token"] not in {view["suggestions"]["token"], edited["suggestions"]["token"]}
    finally:
        release.set()
    assert finished.wait(2)


def test_worker_failure_and_stale_results_do_not_change_the_current_plan(monkeypatch):
    import planning.engine as module
    e, sid = started()
    before = e.store.get(sid).model_dump()
    original = e.suggestions(sid)
    e._base[sid].suggestions.clear()
    monkeypatch.setattr(module, "recommend", lambda *a: (_ for _ in ()).throw(RuntimeError("worker")))
    result = e.suggestions(sid)
    assert result["status"] == "unavailable" and result["items"] == []
    assert e.store.get(sid).model_dump() == before
    e.act(sid, {"type": "drop_place", "place": "b"})
    assert e.suggestions(sid)["token"] != original["token"]


def test_worker_dispatch_failure_still_returns_the_committed_schedule(monkeypatch):
    e, sid = started()
    e.background = True
    monkeypatch.setattr(threading.Thread, "start", lambda *a: (_ for _ in ()).throw(RuntimeError("no thread")))
    view = e.act(sid, {"type": "drop_place", "place": "b"})["view"]
    assert view["metrics"]["cost_unknown"] == 0
    assert view["suggestions"]["status"] == "unavailable"
    assert e.load(sid)["view"]["state"] == view["state"]


def test_day_cache_depends_on_activity_time_preferences_config_and_travel():
    from planning.cache import day_key
    cx = day_ctx([rec("a", 11.94, 108.45), rec("b", 11.941, 108.45)])
    key = day_key(cx, ["a"])
    # A change to a different day's unused place does not invalidate this day.
    assert day_key(replace(cx, places={**cx.places, "b": replace(cx.places["b"], activity="coffee")}), ["a"]) == key
    for changed in [replace(cx, pace="slow"),
                    replace(cx, places={**cx.places, "a": replace(cx.places["a"], activity="coffee", activity_explicit=True)}),
                    replace(cx, time_preferences=({"place_id": "a", "period": "evening"},)),
                    replace(cx, cfg=replace(CFG, buffer_extra_uncertain=999)),
                    replace(cx, rain=0.9), replace(cx, travel=replace(cx.travel, fetched_at="new"))]:
        assert day_key(changed, ["a"]) != key


def test_local_repair_falls_back_when_a_closing_time_requires_reordering():
    from planning.repair import repair_day
    from planning.validate import validate
    cx = day_ctx([rec("a", 11.94, 108.45, hours={"mon": [["10:00", "21:00"]]}),
                  rec("b", 11.941, 108.45, hours={"mon": [["08:00", "09:00"]]}),
                  rec("new", 11.942, 108.45)])
    result = repair_day(["a", "b", "new"], cx, ("a", "b"), set(), CFG)
    assert result.order.index("b") < result.order.index("a")
    assert not validate([cx], [result], [], set(), None, None)


def test_bounded_seven_stop_fallback_can_change_the_first_place():
    from planning.repair import repair_day
    from planning.validate import validate
    records = [rec(pid, 11.94, 108.45, hours={"mon": [["08:00", "09:00"]]} if pid == "b" else
                   {"mon": [["10:00", "21:00"]]} if pid == "a" else "open") for pid in "abcdefg"]
    cx = day_ctx(records)
    result = repair_day(list("abcdefg"), cx, tuple("acdefgb"), set(), CFG)
    assert result.order[0] == "b"
    assert not validate([cx], [result], [], set(), None, None)


def test_day_checks_cache_invalidates_hard_requirements_and_rechecks_global_duplicates():
    from planning.schedule import simulate
    from planning.validate import validate
    cx = day_ctx([rec("a", 11.94, 108.45, group="restaurant", usable=("meal", "backup"))])
    result = simulate(["a"], cx)
    cache = {}
    assert not validate([cx], [result], [], {"a"}, None, None, day_cache=cache)
    hard = [{"feature": "vegetarian_options", "op": "eq", "value": "yes", "unknown_policy": "exclude"}]
    assert any(v.kind == "hard" for v in validate([cx], [result], hard, set(), None, None, day_cache=cache))
    day2 = replace(cx, day=replace(cx.day, index=1))
    assert any(v.kind == "duplicate" for v in validate([cx, day2], [result, result], [], set(), None, None, day_cache=cache))


def test_day_window_edit_reuses_the_other_day_and_cache_stays_bounded():
    e, sid = started()
    e.act(sid, {"type": "move_place", "place": "b", "day": 1})
    before = e._turn_current(e.store.get(sid), e._base[sid])
    edited = e.act(sid, {"type": "set_day_window", "day": 0, "start": "07:00", "end": "22:00"})
    assert edited["diff"]["scope"] == "relayout"
    after = e._turn_current(e.store.get(sid), e._base[sid])
    assert before[1] is after[1]
    assert e.load(sid)["view"]["metrics"]["cost_unknown"] == 1
    assert len(e._base[sid].days) <= CFG.cache_entries


def test_active_backups_do_not_offer_a_selected_backup_or_a_dropped_place():
    e, sid = started()
    e.act(sid, {"type": "add_from_backup", "place": "cafe", "day": 0})
    view = e.act(sid, {"type": "drop_place", "place": "a"})["view"]
    assert all(p["place_id"] != "a" for p in view["backups"]["places"] + view["backups"]["on_delay"])
    assert all(a["id"] != "cafe" for p in view["backups"]["places"] for a in p["alternatives"])
    assert view["robustness"]["level"] in {"solid", "feasible", "fragile"}


def test_suggestions_invalidate_when_only_backup_travel_changes():
    from planning.travel import Travel
    e, sid = started(days=1)
    before = e.suggestions(sid)
    assert any(a["id"] == "cafe" for suggestion in before["items"] for a in suggestion["alternatives"])
    base = e._base[sid]
    old = base.trip.travel
    legs = [[(999, mode) if (old.ids[i] == "cafe" or old.ids[j] == "cafe") and i != j else (minutes, mode)
             for j, (minutes, mode) in enumerate(row)] for i, row in enumerate(old.legs)]
    travel = Travel(old.ids, legs, old.source, old.fetched_at)
    base.trip = replace(base.trip, travel=travel, ctxs=[replace(cx, travel=travel) for cx in base.trip.ctxs])
    after = e.suggestions(sid)
    assert after["token"] != before["token"]
    assert not any(a["id"] == "cafe" for suggestion in after["items"] for a in suggestion["alternatives"])
