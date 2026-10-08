from fixtures import hard, love, si, srec

from decision.output import build
from decision.pipeline import Data, run, why_not
from decision.session import Drop, Session, State
from decision.settings import default

CFG = default()
FLAT = {"steep_or_stairs": "absent", "scenic_view": "present"}


def data():
    return Data([
        srec("FLAT1", group="nature", features=FLAT),
        srec("FLAT2", group="nature", features=FLAT, lat=11.95),
        srec("STEEP", group="nature", features={"steep_or_stairs": "present", "scenic_view": "present"}),
        srec("UNK", group="nature", features={"scenic_view": "present"}),
        srec("FAR", group="attraction", features={"steep_or_stairs": "absent"}, lat=12.4),
        *[srec(f"CAFE{i}", features={"steep_or_stairs": "absent", "cozy_decor": "present"}, lng=108.44 + i / 1000)
          for i in range(4)],
        srec("MEAL", usable=("meal",), features={"steep_or_stairs": "absent"}),
        srec("RENT", usable=()),
    ])


def trip(**over):
    return si(hard_filters=[hard("steep_or_stairs", "present")], soft_weights=[love("scenic_view")], **over)


def session(search=None, state=None):
    return Session(id="0" * 12, search_input=search or trip(), state=state or State())


def test_shortlist_is_fail_closed_and_grouped():
    v = run(session(), data(), CFG).view
    assert set(v["shortlist"]) == {"FLAT1", "FLAT2", "CAFE0", "CAFE1", "CAFE2", "CAFE3", "MEAL"}
    assert [g["id"] for g in v["groups"]] == ["nature", "chill", "meal"]
    assert all(not c["failed"] and not c["unverified"] for g in v["groups"] for c in g["cards"])
    assert v["unverified"]["count"] == 1 and v["unverified"]["cards"][0]["id"] == "UNK" and not v["unverified"]["open"]
    assert v["excluded"]["by_rule"] == [{"rule": "hard:steep_or_stairs", "label": "Điều kiện “dốc, nhiều bậc ≠ có”", "count": 1}]
    assert v["groups"][0]["cards"][0]["why"][0]["text"] == "View đẹp, 3 người nhắc"


def test_anchors_are_kept_even_when_missing_or_violating():
    s = session(trip(anchors=[{"place_id": "STEEP", "priority": "must"}, {"place_id": "GHOST", "priority": "want"}]),
                State(selected=["STEEP", "GHOST"], locked=["STEEP"]))
    v = run(s, data(), CFG).view
    anchors = v["groups"][0]
    assert anchors["id"] == "anchors" and [c["id"] for c in anchors["cards"]] == ["STEEP", "GHOST"]
    assert anchors["cards"][0]["failed"] == ["Dốc, nhiều bậc: có"]
    assert "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)" in anchors["cards"][1]["warnings"]
    assert "relax" in [c["check"] for c in v["feasibility"]["conflicts"]]
    s.state.selected.remove("GHOST")
    s.state.dropped.append(Drop(place_id="GHOST"))
    assert [c["id"] for c in run(s, data(), CFG).view["groups"][0]["cards"]] == ["STEEP"]  # a dropped anchor is gone


def test_chosen_stay_first_dropped_leave_and_why_not_explains():
    s = session(state=State(selected=["CAFE3"], dropped=[Drop(place_id="FLAT1", reason="far")]))
    res = run(s, data(), CFG)
    chill = next(g for g in res.view["groups"] if g["id"] == "chill")
    assert chill["cards"][0]["id"] == "CAFE3" and chill["cards"][0]["chosen"]
    assert "FLAT1" not in res.view["shortlist"] and res.view["dropped"][0]["reason"] == "far"
    assert why_not(res, "FLAT1", s.search_input, CFG)["reasons"] == ["Bạn đã bỏ nơi này"]
    assert why_not(res, "STEEP", s.search_input, CFG)["reasons"] == ["Bị loại: Dốc, nhiều bậc: có"]
    assert why_not(res, "FAR", s.search_input, CFG)["reasons"][0].startswith("Xa so với")
    assert why_not(res, "NOPE", s.search_input, CFG)["known"] is False


def test_month_only_trip_without_days_runs():
    v = run(session(trip(context={"start_date": None, "month": 12, "days": None})), data(), CFG).view
    assert v["feasibility"]["status"] == "feasible" or v["feasibility"]["status"] == "unknown"
    assert v["known_days"] is False and v["days"][0]["weekday"] is None


def test_suggested_card_after_gap_answer():
    s = session(state=State(suggest_group="chill"))
    cards = [c for g in run(s, data(), CFG).view["groups"] for c in g["cards"]]
    assert [c["id"] for c in cards if c["suggested"]] == [next(c["id"] for c in cards if c["group"] == "chill")]


def test_output_roles_backup_and_context():
    s = session(trip(anchors=[{"place_id": "FLAT1", "priority": "must"}]),
                State(selected=["FLAT1", "CAFE0"], locked=["FLAT1"], relaxed=[("CAFE0", "noise")]))
    s.log.append({"version": 1, "action": {"type": "select", "place_id": "CAFE0"}})
    out = build(s, run(s, data(), CFG), CFG)
    assert [(c["id"], c["role"]) for c in out["confirmed"]] == [("FLAT1", "anchor"), ("CAFE0", "selected")]
    assert out["confirmed"][1]["relaxed"] == ["noise"]
    assert {b["id"] for b in out["backup_pool"]} >= {"FLAT2"} and out["trip_context"]["context"]["days"] == 2
    assert out["decision_log"][0]["action"]["place_id"] == "CAFE0"


def test_no_days_means_no_weekday_checks_even_with_a_start_date():
    tue_only = srec("TUE", group="nature", features=FLAT, hours={"tue": [["08:00", "17:00"]]})
    d = Data([tue_only, srec("OK", group="nature", features=FLAT)])
    s = session(trip(context={"start_date": "2026-12-19", "days": None}))  # a Saturday, no number of days
    v = run(s, d, CFG).view
    assert "TUE" in v["shortlist"] and v["known_days"] is False
    assert all(x["weekday"] is None for x in v["days"])


def many_cafes(n):
    return Data([srec(f"CAFE{i:02d}", features={"steep_or_stairs": "absent", "cozy_decor": "present"},
                      lng=108.44 + i / 1000) for i in range(n)])


def test_window_shows_a_page_and_reports_the_total():
    res = run(session(), many_cafes(40), CFG)
    chill = next(g for g in res.view["groups"] if g["id"] == "chill")
    assert len(chill["cards"]) == CFG.page_size and chill["total"] == 40
    assert any(c["top"] for c in chill["cards"]) and not all(c["top"] for c in chill["cards"])
    assert res.shown["chill"] == [c["id"] for c in chill["cards"]]


def test_chosen_place_stays_where_it_was_in_the_window():
    data = many_cafes(40)
    first = run(session(), data, CFG)
    ids = first.shown["chill"]
    st = State(selected=[ids[5]], shown=first.shown)
    again = run(session(state=st), data, CFG)
    assert again.shown["chill"][5] == ids[5]
    assert again.view["change"]["chill"]["added"] == 0


def test_hard_filter_still_fail_closed_with_full_ranking():
    v = run(session(), data(), CFG).view
    shown = {c["id"] for g in v["groups"] for c in g["cards"]}
    assert "STEEP" not in shown and "UNK" not in shown


def test_backup_pool_holds_the_top_places_not_the_whole_window():
    s = session()
    res = run(s, many_cafes(40), CFG)
    top = {c["id"] for g in res.view["groups"] for c in g["cards"] if c["top"]}
    backup = {b["id"] for b in build(s, res, CFG)["backup_pool"]}
    assert backup == top and len(backup) < len(res.view["shortlist"])
