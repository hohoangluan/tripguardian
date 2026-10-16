from dataclasses import replace

from plan_fixtures import CFG, LODGING, FakeLive, all_days, day_ctx, decision, fake_matrix, fixed_sun, no_geocode, rec

from planning.build import pull_early
from planning.days import _greedy, day_cost
from planning.roles import meal_kind, pin_order, takes_meal_slot
from planning.schedule import pin_window, simulate
from planning.timefit import windows_for


def eat(pid, group, name=None, dishes=(), hours="open"):
    r = rec(pid, 1, 1, usable=("meal", "backup"), group=group, name=name, hours=hours)
    if dishes:
        r["menu"] = {"dishes": [{"name": d} for d in dishes]}
    return r


def test_meal_kind_by_group_and_dishes():
    assert meal_kind(eat("a", "restaurant", "Lẩu gà 668"), CFG) == "main"
    assert meal_kind(eat("b", "restaurant", "Bánh Căn Nhỏ"), CFG) == "breakfast"
    assert meal_kind(eat("c", "restaurant", "Quán X", dishes=["Phở bò"]), CFG) == "breakfast"
    assert meal_kind(eat("d", "dessert", "Kem bơ"), CFG) == "light"
    assert meal_kind(eat("e", "cafe", "Coffee"), CFG) == "light"
    assert meal_kind(eat("f", "market", "Chợ đêm", hours={d: [["17:00", "23:00"]] for d in
                                                         ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}), CFG) == "night_meal"
    assert meal_kind(rec("g", 1, 1, group="attraction"), CFG) is None


def test_dawn_wins_over_sunset_unless_the_user_wants_sunset():
    assert pin_order(("sunset_view", "cloud_hunting"), set()) == ("cloud_hunting", "sunset_view")
    assert pin_order(("sunset_view", "cloud_hunting"), {"sunset_view"}) == ("sunset_view",)


def test_a_dessert_shop_never_takes_the_dinner_slot():
    cx = day_ctx([eat("kem", "dessert", "Kem bơ"), rec("ga", 1, 1)], start=900, end=1260,
                 start_node="h", end_node="h", extra_nodes=["h"])
    r = simulate(["ga", "kem"], cx)
    dinner = [i for i in r.items if i.kind == "meal_free" and i.name == "dinner"]
    kem = next(i for i in r.items if i.kind == "visit" and i.place_id == "kem")
    assert dinner, "dinner stays a free meal block"
    assert not (dinner[0].start <= kem.start < dinner[0].end)
    assert not [v for v in r.violations if v.kind == "meal_window"]


def test_a_market_without_evening_hours_or_without_hours_has_no_role():
    daytime = rec("m", 1, 1, group="market", usable=("meal", "backup"), hours=all_days("06:00", "17:00"))
    unknown = rec("n", 1, 1, group="market", usable=("meal", "backup"), hours=None)
    assert meal_kind(daytime, CFG) is None
    assert meal_kind(unknown, CFG) is None


def test_a_light_place_is_not_a_closed_meal_in_the_day_split():
    cx = day_ctx([eat("kem", "dessert", "Kem bơ")] + [rec(f"g{i}", 1, 1) for i in range(5)])
    assert cx.places["kem"].kind == "meal" and not takes_meal_slot(cx.places["kem"])
    assert day_cost(["g0", "kem"], cx) < cx.cfg.weights["closed"]       # one "closed" place would cost the full weight
    out = _greedy([["g0", "g1", "g2"], ["kem"], ["g3"], ["g4"]], [cx, replace(cx)])
    assert out == [["g0", "g1", "g2"], ["kem", "g3", "g4"]]            # the snack goes to the lighter day


def test_a_cafe_the_user_chose_for_photos_keeps_the_photo_windows():
    cx = day_ctx([rec("cafe", 11.94, 108.45, group="cafe", features={"photo_spot": "present"})])
    cafe = replace(cx.places["cafe"], activity="photography", activity_explicit=True)
    cx = replace(cx, places={"cafe": cafe}, purpose="photo")
    assert cafe.meal_kind == "light"
    assert [r.reason for r in windows_for(cafe, cx)] == ["daylight_photography"]
    plain = replace(cafe, activity="coffee", activity_explicit=False)
    assert [r.reason for r in windows_for(plain, replace(cx, places={"cafe": plain}))] == ["light_snack"]


def test_a_cloud_hunting_hill_that_is_also_a_sunset_view_pulls_a_later_day_to_dawn():
    cx = day_ctx([rec("hill", 1, 1, hours=None, features={"cloud_hunting": "present", "sunset_view": "present"})],
                 sun=(360, 1050), start=480)
    hill = replace(cx.places["hill"], pins=pin_order(cx.places["hill"].pins, set()))
    later = replace(cx, places={"hill": hill}, day=replace(cx.day, index=1))
    assert hill.pins == ("cloud_hunting", "sunset_view")
    assert pin_window(hill, later) == (330, 420)               # dawn, although it starts before the 08:00 day
    pulled, who = pull_early(later, ["hill"], later.places, later.travel)
    assert who == "hill" and pulled.day.start <= 330
    first = replace(later, day=replace(later.day, index=0, start_by_user=True))   # day one opens at the user's arrival:
    assert pin_window(hill, first)[0] > 900                                     # sunset stays


def test_a_released_pin_survives_a_pace_change_and_a_reorder_and_stays_confirmable():
    from planning import Engine
    from planning.session import Store
    recs = [rec("park", 11.94, 108.45, features={"sunset_view": "present"}, hours=all_days("00:00", "23:59")),
            rec("temple", 11.95, 108.46, hours=all_days("06:00", "20:00")),
            rec("station", 11.941, 108.451, features={"live_music": "present"}, hours=all_days("00:00", "23:59"))]
    d = decision(["park", "temple", "station"], days=1, leave_at="18:00")      # sunset and 18:00 music do not fit the day
    d["feasibility"] = {"status": "partial", "conflicts": [{"check": "time"}]}
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=fixed_sun, route_fn=lambda *a: None, background=False)
    sid = e.create(d)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    for action in ({"type": "set_pace", "level": "slow"},
                   {"type": "reorder", "day": 0, "order": ["temple", "station", "park"]}):
        e.act(sid, action)
        results = e._active_itinerary(e._get(sid), e._base[sid])["results"]
        # Round-4 ruling (spec section 5): only the music, which the 18:00 departure rules out, is given up; the
        # sunset stays held because keeping it breaks no physical limit.
        assert set(results[0].unpinned) == {"station"}, action
        park = next(i for i in results[0].items if i.kind == "visit" and i.place_id == "park")
        assert 16 * 60 + 15 <= park.start <= 17 * 60 + 10, action
    e.act(sid, {"type": "set_lodging", "text": "Chosen hotel", "lat": 11.94, "lng": 108.45})
    assert e.confirm(sid)
