from datetime import date

from trip.prepass import prepass

TODAY = date(2026, 10, 2)


def got(text):
    return {(p.field, p.value if not isinstance(p.value, dict) else p.value["feature"], p.inferred)
            for p in prepass(text, TODAY).proposals}


def test_days():
    assert ("days", 3, False) in got("đi Đà Lạt 3 ngày 2 đêm")
    assert ("days", 2, False) in got("lịch 2N1Đ")
    assert ("days", 3, False) in got("ba ngày thôi")
    assert not any(f == "days" for f, *_ in got("đi 5 người"))


def test_month_and_dates():
    assert ("month", 12, False) in got("tháng 12 đi")
    g = got("đi từ 12-14/12")
    assert ("start_date", date(2026, 12, 12), False) in g and ("days", 3, False) in g
    assert ("start_date", date(2027, 1, 5), False) in got("ngày 5/1")


def test_companions_and_signals():
    g = got("Đi với ba má, mẹ đau gối")
    assert ("companions", "parents", False) in g
    assert ("signal", "elderly", True) in g and ("signal", "knee", False) in g


def test_quote_is_the_users_own_words():
    p = next(p for p in prepass("Mẹ Đau Gối lắm", TODAY).proposals if p.field == "signal")
    assert p.quote == "Đau Gối"


def test_mobility_people_budget():
    g = got("4 người đi xe máy, không quá 300k/người")
    assert ("mobility", "motorbike", False) in g and ("people", 4, False) in g and ("budget_vnd", 300_000, False) in g


def test_chill_is_ambiguous_and_single_meaning_is_soft():
    r = prepass("muốn chill, săn mây", TODAY)
    assert r.ambiguous[0][0] == "chill" and "noise=quiet" in r.ambiguous[0][1]
    assert any(p.field == "soft" and p.value == ("cloud_hunting=present", "love") for p in r.proposals)


def test_effort_words_become_hard_filters():
    assert ("hard", "steep_or_stairs", False) in got("tránh dốc giúp mình")
    assert ("hard", "long_walk", False) in got("mẹ ngại đi bộ")


def test_lookalike_words_do_not_trigger():
    g = got("mê chụp ảnh bầu trời, bỏ qua, không cần view")
    assert not any(f in ("signal", "companions") for f, *_ in g)
    fields = {(f, v) for f, v, _ in g}
    assert ("soft", ("scenic_view=present", "love")) not in fields


ORDINARY = [  # everyday sentences that are not trip facts (final review, issue 1)
    ("mình bay ngày 12/12", "days"), ("đi sau ngày 20 nhé", "days"), ("một ngày đi được mấy chỗ?", "days"),
    ("300k cho mỗi người", "novelty"), ("không đi với bố mẹ", "companions"), ("để lại dấu chân ở Đà Lạt", "signal"),
    ("mình không say xe", "signal"), ("đám con gái tụi mình", "companions"), ("mình có thắc mắc", "soft"),
    ("phòng có lò sưởi", "soft"), ("nhân viên lịch sự", "soft"), ("mình làm việc ở Sài Gòn", "soft"),
    ("không thích chỗ có view", "soft"), ("1/2 ngày thôi", "start_date"), ("1/2 ngày thôi", "days"),
]


def test_ordinary_sentences_are_not_trip_facts():
    wrong = [(t, f) for t, f in ORDINARY if any(p.field == f for p in prepass(t, TODAY).proposals)]
    assert wrong == []


def test_negated_transport_falls_through_to_the_real_one():
    g = got("mình không chạy xe máy được, đi grab")
    assert ("mobility", "ride", False) in g and ("mobility", "motorbike", False) not in g


def test_number_words_still_count_days():
    assert ("days", 7, False) in got("đi bảy ngày")
    assert ("days", 4, False) in got("chuyến 4 ngày")
