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
