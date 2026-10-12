"""What the serving `details` of a place change in a plan: cost, hours of the day, last entry, season, night roads,
what to prepare. No details -> the old behaviour (every other planning test)."""

from dataclasses import replace
from datetime import date

from plan_fixtures import CFG, day_ctx, decision, rec

from planning import details as dt
from planning import places as pl
from planning.backup import backups
from planning.conditions import DayCond
from planning.objectives import metrics
from planning.route import order_day
from planning.schedule import pin_window, simulate
from planning.timefit import visit_score


def item(text, **kw):
    return {"text": text, "n": 2, "status": "VERIFIED", "reason": None, "evidence": [], **kw}


def timing(**kw):
    base = {"best_time": {"by_time_of_day": {}, "hours": [], "items": []},
            "avoid_time": {"by_time_of_day": {}, "hours": [], "items": []},
            "best_months": [], "avoid_months": [], "schedule": [], "last_entry": None}
    return {**base, **kw}


def cost(base, with_extras=None, per_party=()):
    return {"entry": {}, "parking": None, "extras": [], "per_party": list(per_party),
            "total_vnd": {"base": base, "with_extras": with_extras or base}, "kind": "estimate"}


JEEP = item("jeep 1.200.000/xe", amount_vnd=1_200_000, unit="vehicle")
OP = {"entry_fee": {"typical_vnd": 50000}}


def test_cost_of_takes_the_detail_total_and_divides_party_prices_by_the_people_going():
    assert pl.cost_of(OP) == 50000
    assert pl.cost_of(OP, {"cost": cost(60000)}, 4) == 60000
    assert pl.cost_of(OP, {"cost": cost(60000, per_party=[JEEP])}, 1) == 60000 + 1_200_000
    assert pl.cost_of(OP, {"cost": cost(60000, per_party=[JEEP])}, 4) == 60000 + 300_000
    assert pl.cost_of(OP, {"cost": {**cost(60000), "total_vnd": None}}, 1) == 50000  # no total: the old formula
    assert pl.cost_of({}, {"cost": cost(60000)}, 1) == 60000 and pl.cost_of({}, {}, 1) is None


def test_a_place_carries_the_cost_for_the_trips_party():
    r = rec("a", 11.94, 108.45, details={"cost": cost(60000, per_party=[JEEP])})
    d = decision(["a"])  # the fixture's party is 2
    [p], _ = pl.build_places(d, {"a": r}, CFG)
    assert p.cost_vnd == 60000 + 600_000
    assert pl.build_places(decision(["a"]), {"a": rec("a", 11.94, 108.45)}, CFG)[0][0].cost_vnd is None


def test_metrics_add_what_the_extras_could_cost_at_most():
    cx = day_ctx([rec("a", 11.94, 108.45, details={"cost": cost(60000, 100000)}),
                  rec("b", 11.941, 108.45, details={"cost": cost(20000, 25000)}), rec("c", 11.942, 108.45)])
    r = order_day(sorted(cx.places), cx)
    assert metrics([cx], [r])["extras_max_vnd"] == 40000 + 5000


def best_then_avoid():
    return {"timing": timing(best_time={"by_time_of_day": {"morning": 2}, "hours": [], "items": [item("đi sáng")]},
                             avoid_time={"by_time_of_day": {"afternoon": 2}, "hours": [], "items": [item("trưa nắng")]})}


def test_a_visit_in_the_best_time_scores_better_than_in_the_time_to_avoid():
    cx = day_ctx([rec("a", 11.94, 108.45, details=best_then_avoid()), rec("b", 11.941, 108.45)])
    a, b = cx.places["a"], cx.places["b"]
    assert visit_score(a, 540, 600, cx)[0] < visit_score(a, 840, 900, cx)[0]  # 09:00 morning vs 14:00 afternoon
    assert visit_score(a, 540, 600, cx)[0] < visit_score(b, 540, 600, cx)[0]
    assert visit_score(b, 540, 600, cx)[0] == visit_score(b, 840, 900, cx)[0]  # no details: no preference
    both = {"timing": timing(best_time={"by_time_of_day": {"morning": 2}, "hours": [], "items": []},
                             avoid_time={"by_time_of_day": {"morning": 2}, "hours": [], "items": []})}
    c = day_ctx([rec("c", 11.94, 108.45, details=both)]).places["c"]
    assert visit_score(c, 540, 600, cx)[0] == visit_score(b, 540, 600, cx)[0]  # both at once: they cancel


def last_entry(time, source):
    return {"timing": timing(last_entry={"time": time, "source": source})}


def test_an_official_last_entry_is_a_latest_start_a_review_one_is_not():
    official = day_ctx([rec("a", 11.94, 108.45, details=last_entry("16:00", "official"))], start=1020)  # day opens 17:00
    assert pin_window(official.places["a"], official)[1] == 16 * 60
    late = simulate(["a"], official)
    assert [v.kind for v in late.violations] == ["hours"]
    early = day_ctx([rec("a", 11.94, 108.45, details=last_entry("16:00", "official"))], start=900)
    ok = simulate(["a"], early)
    assert not ok.violations and next(i for i in ok.items if i.kind == "visit").start <= 960
    review = day_ctx([rec("a", 11.94, 108.45, details=last_entry("16:00", "reviews"))], start=1020)
    assert not simulate(["a"], review).violations  # scheduled all the same; the plan warns instead


def test_riding_a_motorbike_home_after_dark_on_a_dangerous_road_costs_score():
    risky = rec("a", 11.94, 108.45, features={"night_road_risk": "present"})
    cx = replace(day_ctx([risky], sun=(360, 1050)), mobility="motorbike")
    early, late = visit_score(cx.places["a"], 900, 960, cx)[0], visit_score(cx.places["a"], 1020, 1080, cx)[0]
    assert late > early
    car = replace(cx, mobility="car")
    assert visit_score(car.places["a"], 1020, 1080, car)[0] == visit_score(car.places["a"], 900, 960, car)[0]
    safe = replace(day_ctx([rec("b", 11.94, 108.45)], sun=(360, 1050)), mobility="motorbike")
    assert visit_score(safe.places["b"], 1020, 1080, safe)[0] == visit_score(safe.places["b"], 900, 960, safe)[0]
    unknown_sun = replace(day_ctx([risky]), mobility="motorbike")  # no sunset known: nothing guessed
    assert visit_score(unknown_sun.places["a"], 1020, 1080, unknown_sun)[0] == visit_score(unknown_sun.places["a"], 900, 960, unknown_sun)[0]


def planned(recs, *, d=None, start=480, sun=None, mobility="motorbike", on=date(2026, 7, 4)):
    """(ctxs, results, decision) of one dated day holding recs."""
    cx = replace(day_ctx(recs, start=start, sun=sun, weekday=("mon", "tue", "wed", "thu", "fri", "sat", "sun")[on.weekday()]),
                 mobility=mobility)
    cx = replace(cx, day=replace(cx.day, date=on))
    r = order_day(sorted(cx.places), cx)
    return [cx], [r], d or decision([x["id"] for x in recs], mobility=mobility, start_date=on.isoformat())


def test_warnings_for_a_season_to_avoid_a_review_last_entry_and_a_dark_road():
    month_bad = rec("a", 11.94, 108.45, details={"timing": timing(avoid_months=[7], best_months=[11])})
    cxs, rs, d = planned([month_bad])
    out = dt.plan_notes(cxs, rs, d)
    assert [w["code"] for w in out["warnings"]] == ["season_avoid"] and "tháng 7" in out["warnings"][0]["text"]
    good = planned([rec("a", 11.94, 108.45, details={"timing": timing(best_months=[7])})])
    assert [c["kind"] for c in dt.plan_notes(*good)["checklist"]] == ["season"]
    shaky = rec("a", 11.94, 108.45, details=last_entry("08:00", "reviews"))
    cxs, rs, d = planned([shaky], start=600)  # visits from 10:00, after a last entry of 08:00 per reviews
    assert [w["code"] for w in dt.plan_notes(cxs, rs, d)["warnings"]] == ["last_entry_review"]
    dark = rec("a", 11.94, 108.45, features={"night_road_risk": "present"})
    cxs, rs, d = planned([dark], start=1000, sun=(360, 1050))
    assert [w["code"] for w in dt.plan_notes(cxs, rs, d)["warnings"]] == ["night_road"]
    assert dt.plan_notes(*planned([rec("a", 11.94, 108.45)]))["warnings"] == []


def test_the_checklist_collects_what_to_bring_book_and_watch_for():
    r = rec("a", 11.94, 108.45, features={"cold": "present", "scam_stage": "parking", "fog_blocks_view": "present"},
            details={"bring": [item("áo ấm")], "booking": [item("đặt qua Zalo")],
                     "timing": timing(schedule=[item("đêm nhạc", days=["sat"])])})
    cxs, rs, d = planned([r])
    got = {c["kind"]: c["text"] for c in dt.plan_notes(cxs, rs, d)["checklist"]}
    assert set(got) == {"bring", "booking", "scam", "cold", "schedule"}  # no fog forecast: no fog line
    assert "áo ấm" in got["bring"] and "đặt qua Zalo" in got["booking"] and "đêm nhạc" in got["schedule"]
    assert "gửi xe" in got["scam"]
    foggy = dt.plan_notes(cxs, rs, d, weather={"2026-07-04": {"fog": True}})["checklist"]
    assert "fog" in {c["kind"] for c in foggy}
    other_day = planned([r], on=date(2026, 7, 5))  # a Sunday: the weekday of the day decides
    assert "schedule" not in {c["kind"] for c in dt.plan_notes(*other_day)["checklist"]}


def test_a_peak_day_prefers_the_quieter_look_alike_as_backup():
    busy = rec("a", 11.94, 108.45, features={"crowd": "high"}, group="cafe",
               details={"relations": {"quieter": ["far"], "busier": []}})
    pool = [rec("near", 11.9425, 108.4525, group="cafe"), rec("far", 11.9435, 108.4535, group="cafe")]
    cx = day_ctx([busy])
    cx = replace(cx, cond=DayCond(crowd="peak", day_type="holiday"))
    r = order_day(["a"], cx)
    d = decision(["a"])
    d["backup_pool"] = [{"id": p["id"], "name": p["id"], "for": None, "reason": "next_best"} for p in pool]
    got = backups([cx], [r], d, {x["id"]: x for x in [busy, *pool]})["places"][0]
    assert got["reasons"] == ["crowd"] and [x["id"] for x in got["alternatives"]] == ["far", "near"]
    plain = rec("a", 11.94, 108.45, features={"crowd": "high"}, group="cafe")
    cx2 = replace(day_ctx([plain]), cond=DayCond(crowd="peak", day_type="holiday"))
    got2 = backups([cx2], [order_day(["a"], cx2)], d, {x["id"]: x for x in [plain, *pool]})["places"][0]
    assert [x["id"] for x in got2["alternatives"]] == ["near", "far"]  # without the relation: nearest first


def test_a_month_to_avoid_is_a_reason_for_a_backup_that_is_not_avoided_too():
    bad = rec("a", 11.94, 108.45, group="cafe", details={"timing": timing(avoid_months=[7])})
    same = rec("same", 11.9425, 108.4525, group="cafe", details={"timing": timing(avoid_months=[7])})
    ok = rec("ok", 11.9435, 108.4535, group="cafe")
    cx = day_ctx([bad])
    cx = replace(cx, day=replace(cx.day, date=date(2026, 7, 4)))
    d = decision(["a"])
    d["backup_pool"] = [{"id": i, "name": i, "for": None, "reason": "next_best"} for i in ("same", "ok")]
    got = backups([cx], [order_day(["a"], cx)], d, {x["id"]: x for x in (bad, same, ok)})["places"][0]
    assert got["reasons"] == ["season"] and [x["id"] for x in got["alternatives"]] == ["ok"]
    assert "mùa" in got["text"]


def test_the_plan_output_carries_the_checklist_and_the_notes_in_its_warnings():
    from plan_fixtures import CENTRE, prepared, spot
    from planning.build import schedule_trip
    from planning.output import build as build_output
    r = spot("c1", CENTRE, 0, details={"bring": [item("áo ấm")], "timing": timing(avoid_months=[12])})
    d = decision(["c1"], days=1, start_date="2026-12-12")
    trip = prepared(d, [r])
    sched = schedule_trip(trip)
    m = metrics(sched.ctxs, sched.results)
    chosen = {"id": "v1", "objective": "least_travel", "label": "x", "score": [0, 0], "metrics": m, "itinerary": [],
              "travel_load": [], "robustness": {}, "backups": {"places": [], "on_delay": []}, "warnings": [],
              "lodging": {"id": None, "name": None, "price_vnd": None}}
    out = build_output(trip, [chosen], chosen, sched.results, d, {}, object(), route_fn=lambda *a: None)
    assert [c["kind"] for c in out["checklist"]] == ["bring"]
    assert "season_avoid" in [w["code"] for w in out["warnings"]]


def test_each_variant_carries_its_notes_and_the_chosen_one_keeps_them_once():
    from plan_fixtures import CFG, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip
    from planning.variants import build_variants
    d, recs = sample_trip()
    recs[0] = {**recs[0], "details": {"bring": [item("áo ấm")]}}
    out = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix, sun_fn=fixed_sun)
    assert out["variants"] and all("checklist" in v for v in out["variants"])
    assert any(c["kind"] == "bring" for v in out["variants"] for c in v["checklist"])
