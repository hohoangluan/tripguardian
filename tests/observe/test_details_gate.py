from corpus.observe.details_gate import gate_detail
from corpus.ontology import load

ONT = load()
SRC = "Vé 50k/người, xe điện 40k một lượt. Đi tháng 11 có dã quỳ, thứ 7 có đêm nhạc. Mang chó vào được nhưng phải rọ mõm"


def d(**kw):
    base = {"kind": "fee", "text": "xe điện", "amount_vnd": 40000, "audience": "", "unit": "", "min_people": 0,
            "months": [], "days": [], "hour": "", "who": "", "verdict": "", "time_of_day": "unknown",
            "quote": "xe điện 40k một lượt"}
    return {**base, **kw}


def test_keeps_fee_with_amount_in_quote():
    out, why = gate_detail(d(), SRC, ONT)
    assert why is None and out["kind"] == "fee" and out["text"] == "xe điện"
    assert out["detail"]["amount_vnd"] == 40000 and out["detail"]["audience"] is None


def test_drops():
    cases = {"unknown_kind": d(kind="wifi"), "quote_not_in_source": d(quote="xe điện 99k"),
             "text_not_in_quote": d(text="xe buýt"), "amount_not_in_quote": d(amount_vnd=60000),
             "missing_amount_vnd": d(amount_vnd=0), "month_not_in_quote": d(kind="best_time", text="dã quỳ",
             amount_vnd=0, months=[12], quote="tháng 11 có dã quỳ"),
             "day_not_in_quote": d(kind="schedule", text="đêm nhạc", amount_vnd=0, days=["sun"], quote="thứ 7 có đêm nhạc"),
             "missing_who": d(kind="fit", text="phải rọ mõm", amount_vnd=0, verdict="conditional",
                              quote="Mang chó vào được nhưng phải rọ mõm")}
    for reason, item in cases.items():
        assert gate_detail(item, SRC, ONT) == (None, reason), reason


def test_fit_maps_who_and_months_days_kept():
    out, _ = gate_detail(d(kind="fit", text="phải rọ mõm", amount_vnd=0, who="chó", verdict="conditional",
                           quote="Mang chó vào được nhưng phải rọ mõm"), SRC, ONT)
    assert out["detail"]["who"] == "pet" and out["detail"]["verdict"] == "conditional"
    out, _ = gate_detail(d(kind="schedule", text="đêm nhạc", amount_vnd=0, days=["sat"], quote="thứ 7 có đêm nhạc"),
                         SRC, ONT)
    assert out["detail"]["days"] == ["sat"]
