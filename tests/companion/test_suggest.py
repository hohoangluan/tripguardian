from datetime import datetime

from companion import load_settings
from companion.trips import TZ
from companion.suggest import nearby, same_site

HOURS = {"status": "VERIFIED", "value": {d: [["06:00", "22:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}


def f(value="present", n=5):
    return {"value": value, "status": "VERIFIED", "n": n, "distribution": {value: n}, "evidence": ["gmaps:x:0"],
            "confidence": {"agreement": 1.0}, "by_context": {}}


def rec(pid, name, lat, *, group="nature", usable=("experience",), exp=None):
    return {"id": pid, "identity": {"name": name, "lat": lat, "lng": 108.44, "category_group": group},
            "usable_as": list(usable), "operation": {"hours": HOURS, "visit_minutes": {"short": 30}},
            "experience": exp or {}, "service": {}, "effort": {}, "environment": {}}


HERE = rec("hill", "Đồi Đa Phú", 11.940)
RECORDS = {r["id"]: r for r in [
    HERE,
    rec("hill_view", "Viewpoint Săn mây Đồi Đa Phú", 11.9405, exp={"cloud_hunting": f(n=50)}),
    rec("cloud1", "Đồi Mây Trắng", 11.941, exp={"cloud_hunting": f(n=40)}),
    rec("cloud2", "Đồi cỏ hồng", 11.942, exp={"cloud_hunting": f(n=30)}),
    rec("cloud3", "Base Camp", 11.943, exp={"cloud_hunting": f(n=20)}),
    rec("lunch", "Cơm Niêu", 11.944, group="restaurant", usable=("meal",)),
    rec("cafe", "Tiệm Cà Phê", 11.945, group="cafe", usable=("meal", "experience")),
]}
SOFT = [{"feature": "cloud_hunting", "value": "present", "weight": 1}]


def pick(hour, same_group=False):
    return nearby(HERE, RECORDS, when=datetime(2026, 11, 12, hour, 0, tzinfo=TZ), budget_min=None,
                  mobility="motorbike", soft=SOFT, hard=[], skip=set(), cfg=load_settings(), same_group=same_group)


def test_another_spot_of_the_same_hill_is_not_somewhere_else_to_go():
    assert same_site(HERE, RECORDS["hill_view"]) and not same_site(HERE, RECORDS["cloud1"])
    assert "hill_view" not in [n["place_id"] for n in pick(12)] + [n["place_id"] for n in pick(6, same_group=True)]


def test_lunch_hour_puts_places_to_eat_first_and_cloud_hunting_does_not_count_at_noon():
    out = pick(12)
    assert [n["place_id"] for n in out[:2]] == ["lunch", "cafe"]
    assert all("cloud_hunting" not in n["matches"] for n in out)


def test_kinds_are_diverse_and_the_morning_wish_counts_in_the_morning():
    out = pick(15)
    groups = [n["group"] for n in out]
    assert groups[:4].count("nature") == 2 and {"restaurant", "cafe"} <= set(groups[:4])  # the rest only fills
    early = pick(6, same_group=True)
    assert early[0]["place_id"] == "cloud1" and early[0]["matches"] == ["cloud_hunting"]
