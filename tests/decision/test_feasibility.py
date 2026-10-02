from fixtures import feat, si, srec

from decision.feasibility import evaluate, need_buckets, supply
from decision.fit import centers
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
CLOUD = feat("present", n=6, by_context={"time_of_day=early_morning": {"present": 5}, "time_of_day=morning": {"present": 1}})


def cands(*recs, score=0.0):
    out = []
    for i, r in enumerate(recs):
        c = Cand(r, "meal" if r["usable_as"] == ["meal"] else "experience")
        c.score = score + i
        out.append(c)
    return out


def run(chosen, s, anchors=(), locked=(), wanted_timed=frozenset()):
    days = trip_days(s.context, CFG)
    return evaluate(chosen, s, days, s.context.days is not None, set(anchors), set(locked),
                    centers(s, {}, CFG), set(wanted_timed), CFG)


def checks(res):
    return [c["check"] for c in res["conflicts"]]


def test_two_places_two_days_is_feasible_with_slack():
    res = run(cands(srec("A"), srec("B")), si())
    assert res["status"] == "feasible" and res["slack"] > 0 and res["totals"]["places"] == 2


def test_too_much_for_one_day_is_infeasible_and_fix_drops_lowest_score():
    chosen = cands(*[srec(f"P{i}") for i in range(6)])
    res = run(chosen, si(context={"days": 1}))
    assert res["status"] == "infeasible" and "time" in checks(res)
    fix = next(c for c in res["conflicts"] if c["check"] == "time")["fixes"][0]
    assert fix["action"] == {"type": "drop", "place_id": "P0"} and fix["label"] == "Bỏ Nơi P0"


def test_closed_every_day_conflict_offers_wishlist_for_locked():
    c = cands(srec("A"))[0]
    c.checks = [{"kind": "physical", "feature": "hours", "value": None, "op": None, "result": "fail",
                 "reason": "closed_all_trip_days", "policy": None}]
    res = run([c], si(), locked={"A"})
    conflict = next(x for x in res["conflicts"] if x["check"] == "hours")
    assert conflict["physical"] and conflict["fixes"][0]["action"] == {"type": "wishlist", "place_id": "A"}


def test_cloud_hunting_competes_for_early_mornings():
    clouds = [srec(f"C{i}", features={"cloud_hunting": CLOUD}) for i in range(3)]
    s = si(context={"days": 2})
    days = trip_days(s.context, CFG)
    assert need_buckets(cands(clouds[0])[0], {"cloud_hunting"}, False, days, CFG) == frozenset({"early_morning"})
    assert need_buckets(cands(clouds[0])[0], set(), False, days, CFG) is None  # not wanted, not an anchor
    assert need_buckets(cands(clouds[0])[0], set(), True, days, CFG) == frozenset({"early_morning"})  # anchor's top
    assert supply(days, None, CFG)["early_morning"] == 1 and supply(days, 300, CFG)["early_morning"] == 2
    res = run(cands(*clouds), s, wanted_timed={"cloud_hunting"})
    tw = next(c for c in res["conflicts"] if c["check"] == "time_windows")
    assert tw["title"] == "3 nơi cần sáng sớm, chuyến chỉ có 1 buổi như vậy" and tw["fixes"][-1]["action"] is None
    assert any("không trùng sáng sớm" in w for w in res["warnings"])  # open 07:00, best before 07:00
    assert "time_windows" not in checks(run(cands(clouds[0]), s, wanted_timed={"cloud_hunting"}))


def test_night_only_places_need_evenings():
    night = {d: [["18:00", "23:00"]] for d in ("mon", "tue")}
    s = si(context={"days": 2})
    two = cands(srec("N1", hours=night), srec("N2", hours=night))
    assert "time_windows" not in checks(run(two, s))
    three = cands(srec("N1", hours=night), srec("N2", hours=night), srec("N3", hours=night))
    assert "time_windows" in checks(run(three, s))


def test_far_areas_per_day_budget_and_relax():
    far = cands(srec("F1", lat=12.05, area="area-7"), srec("F2", lat=11.82, area="area-8"))
    assert "far_areas" in checks(run(far, si(context={"days": 1})))
    many = cands(*[srec(f"E{i}", visit=(10, 15, 20)) for i in range(6)])
    assert "per_day" in checks(run(many, si(context={"days": 1})))
    pricey = cands(srec("M", price={"min_vnd": 200000, "max_vnd": 200000}, usable=("meal",)))
    assert "budget" in checks(run(pricey, si(context={"days": 1, "budget_vnd": 100000})))
    assert "Chưa biết ngân sách của bạn nên chưa kiểm chi phí" in run(pricey, si())["warnings"]
    kept = cands(srec("K"))[0]
    kept.checks = [{"kind": "hard", "feature": "steep_or_stairs", "value": "present", "op": "ne", "result": "fail",
                    "reason": "hard:steep_or_stairs", "policy": "exclude"}]
    relax = next(c for c in run([kept], si(), locked={"K"})["conflicts"] if c["check"] == "relax")
    assert relax["fixes"][0]["action"] == {"type": "relax", "place_id": "K", "feature": "steep_or_stairs"}


def test_unknown_days_skips_day_checks():
    res = run(cands(*[srec(f"P{i}") for i in range(9)]), si(context={"days": None}))
    assert res["status"] == "unknown" and res["slack"] is None and checks(res) == []


def test_unknown_days_skips_budget_check_and_warns():
    pricey = cands(srec("M", price={"min_vnd": 2000000, "max_vnd": 3000000}, usable=("meal",)))
    res = run(pricey, si(context={"days": None, "budget_vnd": 200000}))
    assert res["status"] == "unknown" and "budget" not in checks(res)
    assert "Chưa biết số ngày nên chưa kiểm chi phí" in res["warnings"]
