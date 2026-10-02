import pytest
from fixtures import feat, si, srec

from decision.compare import compare
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
DAYS = trip_days(si().context, CFG)


def cand(rec, minutes=None, role="experience"):
    c = Cand(rec, role)
    c.minutes, c.center = minutes, "trung tâm Đà Lạt"
    return c


def test_rows_only_where_both_have_evidence_and_differ():
    a = cand(srec("A", features={"crowd": "low", "noise": "quiet", "scenic_view": "present"}), minutes=5)
    b = cand(srec("B", features={"crowd": "high", "noise": "quiet", "parking": feat("hard", n=1)}), minutes=20)
    got = compare(a, b, ["scenic_view"], DAYS, CFG)
    rows = {r["aspect"]: r for r in got["rows"]}
    assert rows["crowd"]["better"] == "a" and rows["crowd"]["a"] == "vắng (3 người)"
    assert "noise" not in rows and "parking" not in rows
    assert rows["scenic_view"]["better"] == "unknown" and rows["scenic_view"]["b"] == "chưa biết"
    dist = next(r for r in got["sacrifice"] if r["aspect"] == "distance")
    assert dist["better"] == "a" and dist["b"] == "≈20 phút"


def test_price_crowd_by_time_and_visit_in_sacrifice():
    cbt = lambda v: {"weekday": {"morning": v, "noon": v, "afternoon": v, "evening": v}}
    a = cand(srec("A", price={"min_vnd": 50000, "max_vnd": 50000}, crowd_by_time=cbt(80), visit=(30, 60, 90)))
    b = cand(srec("B", price={"min_vnd": 150000, "max_vnd": 150000}, crowd_by_time=cbt(20), visit=(30, 90, 120)))
    rows = {r["aspect"]: r for r in compare(a, b, [], DAYS, CFG)["sacrifice"]}
    assert rows["price"]["better"] == "a" and rows["crowd_by_time"]["better"] == "b"
    assert rows["visit"]["better"] == "none"


def test_different_roles_cannot_be_compared():
    with pytest.raises(ValueError):
        compare(cand(srec("A")), cand(srec("B"), role="meal"), [], DAYS, CFG)
