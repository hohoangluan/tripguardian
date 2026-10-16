import re

from plan_fixtures import CENTRE, SOUTH, decision, prepared, rec, spot

from planning.build import schedule_trip
from planning.overload import UNAVAILABLE, plan_or_directions


def trip_of(recs, **kw):
    d = decision([r["id"] for r in recs], base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 **kw)
    return prepared(d, recs)


def heavy(n, **kw):
    return [spot(f"c{i}", CENTRE, i, visit=(120, 150, 180), price={"typical_vnd": 10_000 * (i + 1)}, **kw)
            for i in range(n)]


def test_a_trip_that_fits_has_one_main_plan_and_no_overload():
    out = plan_or_directions(trip_of(heavy(3), days=2))
    assert [v["id"] for v in out["variants"]] == ["main"] and out["overload"] is None


def test_overload_gives_three_directions_each_dropping_just_enough():
    trip = trip_of(heavy(10), days=2)
    out = plan_or_directions(trip)
    ov = out["overload"]
    assert ov and {d["id"] for d in ov["directions"]} <= {"fit", "travel", "cost"}
    for v in out["variants"]:
        kept = set(v["kept"])
        assert not schedule_trip(trip, kept=kept).leftover
        for d in v["dropped"]:                    # just enough: adding any dropped place back does not fit
            assert schedule_trip(trip, kept=kept | {d["place_id"]}).leftover


def test_cost_drops_the_priciest_first_with_the_price_as_reason():
    recs = heavy(10)
    recs[9]["operation"]["entry_fee"] = None      # cost now keeps c9 where fit drops it: cost gets its own card
    cost = next(v for v in plan_or_directions(trip_of(recs, days=2))["variants"] if v["id"] == "cost")
    prices = [d["value"] for d in cost["dropped"]]
    assert prices and prices[0] == 90_000 and all(a > b for a, b in zip(prices, prices[1:]))
    assert all(d["reason"] == f"đắt nhất ~{d['value'] // 1000}k/người" for d in cost["dropped"])


def test_a_price_under_a_thousand_is_written_in_dong_never_as_0k():
    recs = heavy(10)
    for k, r in enumerate(recs):
        r["operation"]["entry_fee"] = {"typical_vnd": 100 * (k + 1)} if k < 9 else None   # cost: its own card
    cost = next(v for v in plan_or_directions(trip_of(recs, days=2))["variants"] if v["id"] == "cost")
    assert cost["dropped"] and all("0k" not in d["reason"] and d["reason"] == f"đắt nhất ~{d['value']}đ/người"
                                   for d in cost["dropped"])


def test_cost_never_drops_unknown_price():
    recs = heavy(10)
    recs[9]["operation"]["entry_fee"] = None      # the priciest has no price now
    out = plan_or_directions(trip_of(recs, days=2))
    cost = next(v for v in out["variants"] if v["id"] == "cost" or "cost" in v.get("merged", []))
    assert "c9" not in {d["place_id"] for d in cost["dropped"]} and cost["compare"]["cost_unknown_n"] >= 1


def test_must_go_is_never_dropped():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={"c0": "anchor"}))
    assert all("c0" in v["kept"] for v in out["variants"])


def test_all_protected_cannot_drop():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={r["id"]: "anchor" for r in recs}))
    assert out["overload"] and all(not d["available"] for d in out["overload"]["directions"])


def test_one_day_short_by_a_little_offers_a_longer_day():
    recs = [spot(f"c{i}", CENTRE, i, visit=(50, 60, 70)) for i in range(4)]
    ov = plan_or_directions(trip_of(recs, days=1))["overload"]
    assert ov and 0 < ov["missing_min"] <= 60
    ext = ov["extend"]
    assert ext and ext["side"] in {"start", "end"} and 0 < ext["per_day_min"] <= 60


def test_all_protected_cards_say_why_they_are_unavailable():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={r["id"]: "anchor" for r in recs}))
    assert all(d["unavailable_reason"] and not d["dropped"] for d in out["overload"]["directions"])
    assert not out["ok"] and out["back_to_decision"]["reason"] == "required_places_do_not_fit"


def test_must_places_overrunning_a_day_drop_the_others():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={f"c{i}": "anchor" for i in range(4)}))
    assert out["overload"] and any(v["available"] for v in out["variants"])
    for v in out["variants"]:
        assert {f"c{i}" for i in range(4)} <= set(v["kept"])
        assert not {d["place_id"] for d in v["dropped"]} & {"c0", "c1"}


def test_fit_drops_the_lowest_utility_first():
    recs = heavy(10)
    d = decision([r["id"] for r in recs], days=2,
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    for k, c in enumerate(d["confirmed"]):
        c["utility"] = 10.0 - k                    # c9 matches the user's taste least
    out = plan_or_directions(prepared(d, recs))
    fit = next(v for v in out["variants"] if v["id"] == "fit")
    assert fit["dropped"][0]["place_id"] == "c9" and fit["dropped"][0]["reason"] == "ít khớp gu nhất"
    values = [x["value"] for x in fit["dropped"]]
    assert values == sorted(values)


def test_budget_never_changes_what_a_direction_drops():
    plain = plan_or_directions(trip_of(heavy(10), days=2))
    tight = plan_or_directions(trip_of(heavy(10), days=2, budget=50_000))
    assert [(v["id"], v["kept"]) for v in plain["variants"]] == [(v["id"], v["kept"]) for v in tight["variants"]]


def test_cost_counts_the_places_without_a_price_and_never_runs_out_into_them():
    recs = heavy(10)
    for r in recs[2:]:
        r["operation"]["entry_fee"] = None          # only c0 and c1 have a price
    out = plan_or_directions(trip_of(recs, days=2))
    cost = next(v for v in out["variants"] if v["id"] == "cost" or "cost" in v.get("merged", []))
    assert {d["place_id"] for d in cost["dropped"]} <= {"c0", "c1"}
    assert not cost["available"] and cost["unavailable_reason"] and cost["unpriced_n"] == 8
    assert cost["compare"]["cost_unknown_n"] == sum(k not in {"c0", "c1"} for k in cost["kept"])


def test_overload_calls_the_scheduler_a_bounded_number_of_times():
    recs = [spot(f"c{i}", CENTRE, i, visit=(60, 90, 120)) for i in range(10)] + \
           [spot(f"s{i}", SOUTH, i, visit=(45, 75, 100)) for i in range(9)]
    out = plan_or_directions(trip_of(recs, days=2))
    assert out["overload"] and out["schedule_calls"] <= 40


def test_an_hour_short_offers_a_longer_day_that_holds_everything():
    from dataclasses import replace
    recs = [spot(f"c{i}", CENTRE, i, visit=(50, 60, 70)) for i in range(10)]
    trip = trip_of(recs, days=2)
    ext = plan_or_directions(trip)["overload"]["extend"]
    assert ext and ext["side"] in {"start", "end"} and 0 < ext["per_day_min"] <= 60
    m = ext["per_day_min"]
    wider = [replace(cx, day=replace(cx.day, start=cx.day.start - m) if ext["side"] == "start" else
                     replace(cx.day, end=cx.day.end + m)) for cx in trip.ctxs]
    assert not schedule_trip(replace(trip, ctxs=wider)).leftover


def test_an_overrun_dropping_cannot_fix_never_empties_a_day_with_room():
    # The must-go place overruns day one by itself; the three small places fit on day two (spec section 7: "Còn chỗ
    # trống thì không bao giờ bỏ nơi"). No direction may drop them, and the card must not claim they are must-go.
    recs = [spot("big", CENTRE, 0, visit=(900, 960, 1000))] + \
           [spot(f"c{i}", CENTRE, i + 1, visit=(60, 60, 60), price={"typical_vnd": 10_000 * (i + 1)}) for i in range(3)]
    out = plan_or_directions(trip_of(recs, days=2, roles={"big": "anchor"}))
    assert out["overload"] and out["variants"]
    for v in out["variants"]:
        assert {"big", "c0", "c1", "c2"} <= set(v["kept"]) and v["dropped"] == [] and not v["available"]
        assert v["unavailable_reason"] == UNAVAILABLE["no_gain"] != UNAVAILABLE["protected"]


def test_travel_drops_the_longest_road_first_and_says_the_minutes_saved():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 150, 180)) for i in range(6)] + \
           [spot(f"s{i}", SOUTH, i, visit=(120, 150, 180)) for i in range(4)]
    d = decision([r["id"] for r in recs], days=2,
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    for c in d["confirmed"]:
        c["utility"] = 5.0 if c["id"].startswith("s") else 1.0     # fit keeps the south places: travel has its own card
    travel = next(v for v in plan_or_directions(prepared(d, recs))["variants"] if v["id"] == "travel")
    gone = travel["dropped"]
    assert gone and gone[0]["place_id"].startswith("s")             # the south is the long way from the lodging
    values = [x["value"] for x in gone]
    assert values == sorted(values, reverse=True)
    for x in gone:
        m = re.fullmatch(r"bớt (\d+)′ đi xe", x["reason"])
        assert m and int(m.group(1)) == x["value"] > 0


def test_travel_measures_from_the_lodging_on_an_arrival_day():
    # Day one starts at the arrival point, 6-7 km north of everything; the lodging is in the centre. "far" is the only
    # place 15′ or more from the lodging, so travel drops it first and says the others are close to the lodging.
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 150, 180)) for i in range(8)] + \
           [rec("far", SOUTH[0] - 0.02, SOUTH[1] - 0.01, area="area-2", visit=(120, 150, 180))]
    d = decision([r["id"] for r in recs], days=2, entry={"text": "airport", "lat": CENTRE[0] + 0.06, "lng": CENTRE[1]},
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    d["trip_context"]["context"]["frame"] = {
        "days": [{"date": f"2026-12-{12 + i}", "start": "08:00", "end": "21:00", "busy": [], "intensity": "normal"}
                 for i in range(2)],
        "arrive": {"at": "2026-12-12T09:00", "how": "plane"}, "leave": None, "drive_day_min": None,
        "meals": {"skip": [], "breakfast_at_lodging": False, "snacks": False, "shift_min": 0},
        "rest": None, "visit": {}}
    for c in d["confirmed"]:
        c["utility"] = 5.0 if c["id"] == "far" else 1.0             # fit keeps "far": travel has its own card
    trip = prepared(d, recs)
    assert trip.days[0].start_node == "@entry" and trip.ctxs[0].home == "@home"
    travel = next(v for v in plan_or_directions(trip)["variants"] if v["id"] == "travel")
    first = travel["dropped"][0]
    assert first["place_id"] == "far" and first["reason"].endswith(", các nơi khác cách chỗ ở < 15′")
