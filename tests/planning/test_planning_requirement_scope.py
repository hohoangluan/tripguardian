from dataclasses import replace

import pytest

from plan_fixtures import CFG, day_ctx, decision, rec

from planning.backup import _fits
from planning.model import DayResult, Item
from planning.places import build_places
from planning.validate import validate


VEG = {"feature": "vegetarian_options", "op": "eq", "value": "yes", "unknown_policy": "exclude"}


def test_lunch_cafe_and_market_are_checked_as_eating():
    records = [rec("cafe", 1, 1, group="cafe", usable=("experience", "meal")),
               rec("market", 1, 1, group="market")]
    d = decision([r["id"] for r in records], hard=[VEG])
    d["trip_context"]["activities"] = {"cafe": "eating", "market": "eating"}
    places, missing = build_places(d, {r["id"]: r for r in records}, CFG)
    assert not missing
    assert all(p.kind == "meal" and p.activity == "eating" for p in places)
    cx = day_ctx(records)
    cx.places.update({p.id: p for p in places})
    items = (Item("visit", 720, 750, place_id="cafe"), Item("visit", 800, 830, place_id="market"))
    result = DayResult(items, ("cafe", "market"), (), 0, 0, 830)
    failures = validate([cx], [result], [VEG], set(), None, None)
    assert [v.place_id for v in failures if v.kind == "hard"] == ["cafe", "market"]


def test_backup_checks_eq_and_unknown_with_the_original_activity():
    source = rec("source", 1, 1, group="restaurant", usable=("meal",), features={"vegetarian_options": "yes"})
    records = [source, rec("no", 1, 1, group="restaurant", usable=("meal",), features={"vegetarian_options": "no"}),
               rec("unknown", 1, 1, group="restaurant", usable=("meal",)),
               rec("yes", 1, 1, group="cafe", usable=("meal",), features={"vegetarian_options": "yes"})]
    cx = day_ctx(records)
    s = cx.places["source"]
    assert not _fits(cx.places["no"], s, [], cx, [VEG])
    assert not _fits(cx.places["unknown"], s, [], cx, [VEG])
    assert _fits(cx.places["yes"], s, [], cx, [VEG])
    flagged = {**VEG, "unknown_policy": "flag"}
    assert _fits(cx.places["unknown"], s, [], cx, [flagged])
    assert not _fits(cx.places["no"], s, [], cx, [flagged])


def test_a_dual_purpose_cafe_can_replace_a_meal_when_its_options_are_verified():
    records = [rec("meal", 1, 1, group="restaurant", usable=("meal",), features={"vegetarian_options": "yes"}),
               rec("cafe", 1, 1, group="cafe", usable=("experience", "meal"), features={"vegetarian_options": "yes"})]
    cx = day_ctx(records)
    assert _fits(cx.places["cafe"], cx.places["meal"], [], cx, [VEG])


def test_raw_scope_cannot_bypass_physical_or_diet_checks():
    from requirements import allowed
    park = rec("park", 1, 1, group="garden_farm", features={"long_walk": "present"})
    physical = {"feature": "long_walk", "op": "ne", "value": "present", "scope": "eating"}
    assert not allowed(park, physical, "sightseeing")
    meal = rec("meal", 1, 1, group="restaurant", features={"vegetarian_options": "no"})
    assert not allowed(meal, {**VEG, "scope": "sightseeing"}, "eating")


@pytest.mark.parametrize("diet,confirmable", [("no", False), ("yes", True)])
def test_swap_keeps_eating_activity_for_cafe_and_revalidates_diet(diet, confirmable):
    from plan_fixtures import FakeLive, fake_matrix, no_geocode
    from planning.engine import Engine, NotConfirmable
    from planning.session import Store

    records = [rec("meal", 11.94, 108.45, group="restaurant", usable=("meal", "backup"),
                   features={"vegetarian_options": "yes"}, price={"typical_vnd": 50000}),
               rec("cafe", 11.941, 108.45, group="cafe", usable=("experience", "meal", "backup"),
                   features={"vegetarian_options": diet})]
    d = decision(["meal"], days=1, hard=[VEG])
    d["backup_pool"] = [{"id": "cafe", "for": "meal"}]
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), matrix_fn=fake_matrix,
               geocode_fn=no_geocode, sun_fn=lambda *a: None, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    e.act(sid, {"type": "swap", "place": "meal", "with": "cafe"})
    places = e._places_for(e.store.get(sid), e._base[sid])
    assert places["cafe"].activity == "eating"
    assert places["cafe"].kind == "meal"
    for action in [{"type": "set_pace", "level": "slow"}, {"type": "set_objective", "name": "least_travel"},
                   {"type": "set_day_window", "day": 0, "start": "08:00", "end": "21:00"}]:
        e.act(sid, action)
    resumed = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=e.store, matrix_fn=fake_matrix,
                     geocode_fn=no_geocode, sun_fn=lambda *a: None, background=False)
    assert resumed.load(sid)["view"]["state"]["activity_override"] == {"cafe": "eating"}
    e = resumed
    if confirmable:
        assert any(i.get("place_id") == "cafe" for d in e.confirm(sid)["itinerary"] for i in d["items"])
    else:
        with pytest.raises(NotConfirmable):
            e.confirm(sid)


def test_adding_a_recommended_coffee_backup_keeps_the_explicit_activity():
    from plan_fixtures import FakeLive, fake_matrix, no_geocode
    from planning.engine import Engine
    from planning.session import Store

    records = [rec("meal", 11.94, 108.45, group="restaurant", usable=("meal", "backup"),
                   features={"vegetarian_options": "yes"}, price={"typical_vnd": 50000}),
               rec("cafe", 11.941, 108.45, group="cafe", usable=("experience", "meal", "backup"),
                   features={"vegetarian_options": "no"}, price={"typical_vnd": 100000})]
    d = decision(["meal"], days=1, hard=[VEG], leave_at="18:00")      # a cafe is a snack: it needs an afternoon gap
    d["backup_pool"] = [{"id": "cafe", "for": "meal"}]
    d["trip_context"]["activities"] = {"cafe": "coffee"}
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), matrix_fn=fake_matrix,
               geocode_fn=no_geocode, sun_fn=lambda *a: None, route_fn=lambda *a: None, background=False)
    sid = e.create(d, None)["id"]
    picked = e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    assert any(a["id"] == "cafe" and a["activity"] == "coffee"
               for s in picked["view"]["recommendations"] for a in s["alternatives"])
    added = e.act(sid, {"type": "add_from_backup", "place": "cafe", "day": 0})
    assert added["view"]["metrics"]["cost_vnd"] == 150000
    assert e.store.get(sid).state.activity_override["cafe"] == "coffee"
    assert any(i.get("place_id") == "cafe" for day in e.confirm(sid)["itinerary"] for i in day["items"])
