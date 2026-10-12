from datetime import date

from corpus.serving import build, check, feature, finish
from corpus.serving.record import config

BUILT = date(2026, 10, 2)
CFG = config()["details"]
GATED = {"correct": 40, "wrong": 0, "precision": 1.0, "lower": 0.91, "gate": True}


def sig(top, dist=None, n=3):
    return {"n": n, "distribution": dist or {top: n}, "top_value": top, "status": "signal", "authority": None,
            "by_context": {}, "mention_rate": 0.1, "needs_review": False, "servable": True, "quality": None,
            "observation_ids": ["x:1"],
            "confidence": {"independent_sources": n, "agreement": 1.0, "freshness_days": 10, "source_types": ["provider"]}}


def cl(text, n=2, authority=False, **kw):
    base = {"text": text, "n": n, "authority": authority, "members": [f"x:{text}"], "evidence": [f"x:{text}"],
            "amount_vnd": None, "audience": None, "unit": None, "min_people": None, "months": {}, "days": {}, "hours": [],
            "time_of_day": {}, "who": None, "verdicts": {}}
    return {**base, **kw}


def intel(fid="F", details=None, features=None, tickets=None, last_entry=None, group="cafe", lat=11.94, lng=108.44,
          voices=30):
    return {"place_fid": fid, "place_name": fid, "as_of": "2026-09-30", "voices": voices,
            "identity": {"category": "Quán cà phê", "lat": lat, "lng": lng, "address": "Đà Lạt"},
            "features": features or {}, "coverage": {"experience": "PARTIAL"}, "details": details or {},
            "operation": {"closure": None, "hours": None, "price_range": None, "crowd_by_time": None,
                          "tickets_vnd": tickets, "last_entry": last_entry},
            "estimates": {"category_group": group, "usable_as_default": ["experience"], "effort_hint": "unknown",
                          "visit_minutes": {"short": 45, "typical": 75, "long": 150, "source": "category_default", "n": 0},
                          "entry_fee": None}}


def rec(quality=None, **kw):
    return build(intel(**kw), BUILT, None, quality)


def test_a_cluster_of_one_author_is_not_served_and_status_follows_the_measured_precision():
    details = {"order": [cl("bánh căn", n=1), cl("mì quảng", n=2)]}
    [item] = rec(details=details)["details"]["order"]
    assert (item["text"], item["n"], item["status"], item["reason"], item["evidence"]) == \
        ("mì quảng", 2, "UNCERTAIN", "unmeasured_precision", ["x:mì quảng"])
    assert rec({("detail.order", "*"): GATED}, details=details)["details"]["order"][0]["status"] == "VERIFIED"
    bad = {"correct": 15, "wrong": 15, "precision": 0.5, "lower": 0.33, "gate": False}  # 30 labels, fails the gate
    assert rec({("detail.order", "*"): bad}, details=details)["details"]["order"] == []
    few = {"correct": 3, "wrong": 3, "precision": 0.5, "lower": 0.2, "gate": False}  # too few labels to judge a kind
    assert rec({("detail.order", "*"): few}, details=details)["details"]["order"][0]["status"] == "UNCERTAIN"
    official = {"fee": [cl("vé", n=1, authority=True, amount_vnd=50000)]}
    assert rec(details=official)["details"]["cost"]["entry"]["adult"] == {"vnd": 50000, "source": "official"}
    assert rec()["details"]["order"] == [] and rec()["details"]["cost"] is None and rec()["details"]["timing"]["last_entry"] is None


def test_known_for_is_what_few_places_of_the_group_have():
    def place(fid, *clusters, group="cafe"):
        return build(intel(fid, {"known_for": list(clusters)}, group=group), BUILT)
    a = place("A", cl("xích đu nhìn hồ", n=3), cl("view đồi", n=4))
    b, c = place("B", cl("view đồi", n=2)), place("C", cl("Có view đồi", n=2))
    d = place("D", cl("xích đu nhìn hồ", n=3), group="restaurant")
    assert "_known_for" in a["details"]
    finish([a, b, c, d], CFG, [])
    assert a["details"]["known_for"]["headline"]["text"] == "xích đu nhìn hồ" and a["details"]["known_for"]["more"] == []
    assert b["details"]["known_for"] == {"headline": None, "more": []}  # every place of the group has it
    assert c["details"]["known_for"]["headline"] is None and "_known_for" not in a["details"]
    assert d["details"]["known_for"]["headline"] is None  # alone in its group: nothing to be rare against


def test_cost_adds_entry_parking_and_extras_for_one_person_and_keeps_party_prices_apart():
    fees = [cl("gửi xe máy", amount_vnd=10000, unit="vehicle"), cl("xe điện", amount_vnd=40000, unit="item"),
            cl("jeep 1.200.000/xe", amount_vnd=1200000, unit="vehicle")]
    cost = rec(details={"fee": fees}, tickets={"adult": [50000], "child": [30000], "senior": []})["details"]["cost"]
    assert cost["entry"]["adult"] == {"vnd": 50000, "source": "official"} and cost["entry"]["child"]["vnd"] == 30000
    assert cost["entry"]["senior"] is None and cost["parking"]["text"] == "gửi xe máy"
    assert [x["text"] for x in cost["extras"]] == ["xe điện"] and [x["text"] for x in cost["per_party"]] == ["jeep 1.200.000/xe"]
    assert cost["per_party"][0]["unit"] == "vehicle" and cost["per_party"][0]["amount_vnd"] == 1200000
    assert cost["total_vnd"] == {"base": 60000, "with_extras": 100000} and cost["kind"] == "estimate"


def test_cost_is_a_fact_only_when_every_part_is_official():
    official = [cl("xe điện", n=1, authority=True, amount_vnd=40000, unit="item")]
    cost = rec(details={"fee": official}, tickets={"adult": [50000], "child": [], "senior": []})["details"]["cost"]
    assert cost["total_vnd"] == {"base": 50000, "with_extras": 90000} and cost["kind"] == "fact"


def test_review_ticket_fills_in_and_official_wins():
    review = [cl("vé người lớn", amount_vnd=60000, audience="adult"), cl("vé trẻ em", amount_vnd=20000, audience="child")]
    cost = rec(details={"fee": review})["details"]["cost"]
    assert cost["entry"]["adult"] == {"vnd": 60000, "source": "reviews"} and cost["entry"]["child"]["vnd"] == 20000
    cost = rec(details={"fee": review}, tickets={"adult": [50000], "child": [], "senior": []})["details"]["cost"]
    assert cost["entry"]["adult"] == {"vnd": 50000, "source": "official"} and cost["entry"]["child"]["source"] == "reviews"


def test_no_adult_ticket_means_no_total_unless_entry_is_free():
    fees = {"fee": [cl("xe điện", amount_vnd=40000, unit="item")]}
    cost = rec(details=fees)["details"]["cost"]
    assert cost["total_vnd"] is None and [x["text"] for x in cost["extras"]] == ["xe điện"]
    free = rec(details=fees, features={"entry_fee": sig("free")})["details"]["cost"]
    assert free["entry"]["adult"] == {"vnd": 0, "source": "reviews"}
    assert free["total_vnd"] == {"base": 0, "with_extras": 40000}


def test_timing_months_need_two_authors_or_a_season_row_and_official_last_entry_wins():
    details = {"best_time": [cl("dã quỳ nở", months={"11": 2, "12": 1}, time_of_day={"morning": 2}, hours=["06:00"]),
                             cl("đi sớm", time_of_day={"early_morning": 2})],
               "avoid_time": [cl("mùa mưa", n=1, months={"7": 1})],
               "schedule": [cl("đêm nhạc", days={"sat": 2})],
               "last_entry": [cl("ngừng bán vé", hours=["16:30"])]}
    r = rec(details=details, last_entry="16:00")
    t = r["details"]["timing"]
    assert t["best_months"] == [11] and t["avoid_months"] == [] and t["last_entry"] == {"time": "16:00", "source": "official"}
    assert t["best_time"]["by_time_of_day"] == {"morning": 2, "early_morning": 2} and t["best_time"]["hours"] == ["06:00"]
    assert [x["text"] for x in t["best_time"]["items"]] == ["dã quỳ nở", "đi sớm"] and t["avoid_time"]["items"] == []
    assert t["schedule"][0]["days"] == ["sat"]
    assert rec(details=details)["details"]["timing"]["last_entry"] == {"time": "16:30", "source": "reviews"}
    finish([r], CFG, [{"match": "Dã Quỳ", "months": [10, 11], "source": "https://x"},
                      {"match": "mùa mưa", "months": [7, 8], "source": "https://y"}])
    assert r["details"]["timing"]["best_months"] == [10, 11] and r["details"]["timing"]["avoid_months"] == []  # n=1 not served


def test_fit_serves_a_companion_from_two_authors_and_check_reads_it():
    one = {"fit": [cl("toàn bậc thang", n=1, who="baby", verdicts={"bad": 1})]}
    assert rec({("detail.fit", "*"): GATED}, details=one)["details"]["fit"] == {}
    two = {"fit": [cl("toàn bậc thang", n=2, who="baby", verdicts={"bad": 2}),
                   cl("có khu cho bé", n=1, who="kids", verdicts={"good": 1})]}
    r = rec({("detail.fit", "*"): GATED}, details=two)
    baby = r["details"]["fit"]["baby"]
    assert (baby["value"], baby["distribution"], baby["n"], baby["status"], baby["reasons"]) == \
        ("bad", {"bad": 2}, 2, "VERIFIED", ["toàn bậc thang"]) and "kids" not in r["details"]["fit"]
    assert feature(r, "fit.baby")["value"] == "bad" and feature(r, "fit.pet") is None
    assert check(r, "fit.baby", "bad") == "fail" and check(r, "fit.pet", "bad") == "unknown"
    assert check(rec(details=two), "fit.baby", "bad") == "unknown"  # precision of fit not measured yet: not firm


def test_fit_splits_verdicts_and_a_tie_takes_the_worse_one():
    two = {"fit": [cl("phải rọ mõm", n=1, who="pet", verdicts={"conditional": 1}),
                   cl("không cho chó vào", n=1, who="pet", verdicts={"bad": 1})]}
    pet = rec({("detail.fit", "*"): GATED}, details=two)["details"]["fit"]["pet"]
    assert (pet["value"], pet["distribution"], pet["n"]) == ("bad", {"bad": 1, "conditional": 1}, 2)
    assert pet["reasons"] == ["không cho chó vào", "phải rọ mõm"]


def test_relations_need_both_signals_to_point_the_same_way():
    def place(fid, voices, high, low):
        r = build(intel(fid, voices=voices, features={"crowd": sig("high", {"high": high, "low": low}, high + low)}), BUILT)
        r["near_duplicate_group"] = 0
        return r
    a, b = place("A", 10, 1, 4), place("B", 50, 4, 1)
    finish([a, b], CFG, [])
    assert a["details"]["relations"] == {"quieter": [], "busier": ["B"]}
    assert b["details"]["relations"] == {"quieter": ["A"], "busier": []}
    a, b = place("A", 10, 1, 4), place("B", 50, 1, 4)  # more voices but not more crowded
    c = place("C", 5, 4, 1)  # fewer voices, more crowded than A: opposite directions
    finish([a, b, c], CFG, [])
    assert a["details"]["relations"] == {"quieter": [], "busier": []} and c["details"]["relations"]["quieter"] == []


def test_walk_to_the_night_market_is_kept_within_twenty_minutes():
    market = build(intel("M"), BUILT)
    near = build(intel("N", lat=11.94 + 0.0036), BUILT)  # about 400 m
    far = build(intel("Z", lat=11.94 + 0.027), BUILT)  # about 3 km
    nowhere = build(intel("X", lat=None, lng=None), BUILT)
    finish([market, near, far, nowhere], {**CFG, "night_market_fid": "M"}, [])
    assert [r["details"]["walk_to_night_market_min"] for r in (market, near, far, nowhere)] == [None, 7, None, None]
    other = build(intel("N", lat=11.94 + 0.0036), BUILT)
    finish([other], CFG, [])
    assert other["details"]["walk_to_night_market_min"] is None
