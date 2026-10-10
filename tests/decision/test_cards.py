from fixtures import feat, si, srec

from decision.cards import card, phrase, price_text
from decision.model import Cand
from decision.settings import default

CFG = default()


def cand(rec, **kw):
    c = Cand(rec, "experience")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_why_comes_from_matches_anchor_and_nearness():
    c = cand(srec("A"), matches=[("scenic_view", "present", 1.0, 7), ("crowd", "low", 0.5, 4)], minutes=8,
             center="trung tâm Đà Lạt")
    got = card(c, si(), CFG, anchor=True)["why"]
    assert [w["text"] for w in got] == ["Nơi bạn muốn đến", "View đẹp, 7 người nhắc", "Độ đông: vắng, 4 người nhắc"]
    assert got[1]["sid"] == "scenic_view"
    near = card(cand(srec("B"), minutes=8, center="trung tâm Đà Lạt"), si(), CFG)["why"]
    assert near == [{"text": "Gần trung tâm Đà Lạt, ≈8 phút (ước tính)", "sid": None}]


def test_tradeoffs_flags_avoided_matches_and_bad_firm_values():
    rec = srec("A", features={"noise": feat("loud", n=5), "parking": feat("hard", n=1)})
    c = cand(rec, flags=[{"code": "rain", "text": "Ngoài trời", "sid": "setting"},
                         {"code": "rough_road", "text": "Đường vào xấu", "sid": "rough_road_access"}],
             matches=[("live_music", "present", -1.0, 3)])
    out = card(c, si(), CFG)
    texts = [t["text"] for t in out["tradeoffs"]]
    assert texts == ["Đường vào xấu", "Nhạc sống, điều bạn muốn tránh", "Độ ồn: ồn, theo 5 người"]
    assert out["outdoor"]  # rain is trip-wide (view notes); the card only says it is outdoors


def test_confidence_levels_follow_wanted_features():
    rec = srec("A", voices=50, features={"scenic_view": "present", "noise": feat("quiet", status="UNCERTAIN")})
    assert card(cand(rec), si(), CFG, wanted=["scenic_view"])["confidence"]["level"] == "high"
    assert card(cand(rec), si(), CFG, wanted=["scenic_view", "noise"])["confidence"]["level"] == "medium"
    low = card(cand(rec), si(), CFG, wanted=["hiking", "noise", "scenic_view"])["confidence"]
    assert low["level"] == "low" and "chưa có bằng chứng về leo núi, trekking" in low["reason"]
    assert card(cand(rec), si(), CFG)["confidence"]["level"] == "high"  # nothing wanted: by voices


def test_price_unknown_budget_warnings_failed_and_declined():
    rec = srec("A", price={"min_vnd": 100000, "max_vnd": 200000}, rating_trend={"direction": "falling"})
    c = cand(rec, warnings=["hours_outdated", "uncertain_value:noise"],
             checks=[{"kind": "hard", "feature": "steep_or_stairs", "value": "present", "op": "ne", "result": "fail",
                      "reason": "hard:steep_or_stairs", "policy": "exclude"},
                     {"kind": "hard", "feature": "long_walk", "value": "present", "op": "ne", "result": "unknown",
                      "reason": "hard:long_walk", "policy": "flag"}])
    got = card(c, si(unknowns=["budget_vnd"]), CFG)
    assert price_text(rec) == "100k–200k/người"
    band = lambda lo, hi: price_text(srec("P", price={"min_vnd": lo, "max_vnd": hi}))  # noqa: E731
    assert band(1, 100000) == "dưới 100k/người"  # Google's "₫1–100K": never "0k–100k"
    assert band(500000, None) == "từ 500k/người" and band(80000, 80000) == "khoảng 80k/người"
    assert band(1000000, 1500000) == "1 triệu–1,5 triệu/người"
    fee = srec("F", entry_fee={"min_vnd": 25000, "typical_vnd": 75000, "max_vnd": 150000})
    assert card(cand(fee), si(), CFG)["price"] == "vé khoảng 75k"
    assert card(cand(srec("G", features={"entry_fee": feat("free", n=4)})), si(), CFG)["price"] == "vào cửa miễn phí"
    assert got["depends_on_unknown"] == "Chưa biết ngân sách của bạn; giá 100k–200k/người"
    assert got["warnings"] == ["Giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến", "Độ ồn: chưa xác nhận chắc"]
    assert got["failed"] == ["Dốc, nhiều bậc: có"] and got["unverified"] == ["Chưa xác minh được: phải đi bộ xa"]
    assert got["declined"] is True and phrase("crowd", "high", CFG) == "Độ đông: đông"


def test_missing_record_card():
    c = Cand(srec("Z", name=None, hours=None, voices=0), "experience", keep=True, missing=True)
    got = card(c, si(), CFG)
    assert got["confidence"]["level"] == "low" and "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)" in got["warnings"]


def test_card_carries_the_star_fit_or_none_when_the_trip_names_no_taste():
    assert card(cand(srec("A"), stars=4.5), si(), CFG)["fit"] == {"stars": 4.5, "level": "Rất hợp"}
    assert card(cand(srec("B")), si(), CFG)["fit"] is None
