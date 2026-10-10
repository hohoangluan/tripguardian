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
    return Data([srec(f"CAFE{i:02d}", features={"steep_or_stairs": "absent", "cozy_decor": "present", "scenic_view": "present"},
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


def test_lodging_never_reaches_explore():
    hotel = srec("HOTEL", group="stay", category="Khách sạn", usable=(), features={"scenic_view": "present"})
    s = session(trip(anchors=[{"place_id": "HOTEL", "priority": "must"}]), State(selected=["HOTEL"]))
    v = run(s, Data([*data().records, hotel]), CFG).view
    shown = {c["id"] for g in v["groups"] for c in g["cards"] if c["id"] == "HOTEL"}
    assert not shown and "HOTEL" not in v["shortlist"]


def crowd_data():
    from fixtures import feat
    busy = {"scenic_view": "present", "steep_or_stairs": "absent", "crowd": feat("high", n=38, dist={"high": 33, "low": 5})}
    calm = {"scenic_view": "present", "steep_or_stairs": "absent"}
    return Data([srec("BUSY", features=busy), *[srec(f"CALM{i}", features=calm, lng=108.44 + i / 1000) for i in range(3)],
                 srec("HILL", group="nature", features=calm), srec("PLAIN", features={"steep_or_stairs": "absent"})])


def test_a_place_with_a_crowd_warning_is_never_best_fit_when_the_trip_avoids_crowds():
    """Bug D-2: "Độ đông: đông, theo 38 người" carried the "Hợp nhất" badge on a trip that avoids crowds."""
    cards = {c["id"]: c for g in run(session(trip(pace={"crowd_tolerance": "avoid"})), crowd_data(), CFG).view["groups"]
             for c in g["cards"]}
    assert not cards["BUSY"]["top"] and cards["CALM0"]["top"]
    assert not cards["PLAIN"]["top"]  # matches no wish of the trip: listed, never "Hợp nhất"
    cards = {c["id"]: c for g in run(session(), crowd_data(), CFG).view["groups"] for c in g["cards"]}
    assert cards["BUSY"]["top"]  # crowds are fine for this trip


def test_asking_to_drop_crowded_places_removes_them_from_the_list():
    from decision.curation import apply
    st = apply(State(), {"type": "feedback", "reason": "crowded"}, lambda p: True, {}, None, CFG)
    assert st.profile.hide_crowded and st.profile.crowd_tolerance == "avoid"
    res = run(session(state=st), crowd_data(), CFG)
    assert "BUSY" not in res.view["shortlist"] and "CALM0" in res.view["shortlist"]
    assert why_not(res, "BUSY", session(state=st).search_input, CFG)["reasons"][0].startswith("Nhiều người nói")
    kept = run(session(state=st.model_copy(update={"selected": ["BUSY"]})), crowd_data(), CFG).view
    assert "BUSY" in kept["shortlist"]  # a chosen place is never dropped silently


def test_focus_tab_follows_the_trips_main_interest():
    assert run(session(trip(liked_groups=["chill"])), crowd_data(), CFG).view["focus"] == "chill"
    nature = Data([srec(f"H{i}", group="nature", features=FLAT, lng=108.44 + i / 1000) for i in range(4)]
                  + [srec("C", features={"steep_or_stairs": "absent"})])
    assert run(session(), nature, CFG).view["focus"] == "nature"  # no named interest: where the best fits are


def test_the_rain_warning_is_said_once_for_the_trip_not_on_every_card():
    """Bug D-5: every outdoor card carried "Ngoài trời, tháng 10 hay mưa" as its trade-off."""
    out = {"scenic_view": "present", "steep_or_stairs": "absent", "setting": "outdoor"}
    d = Data([srec(f"OUT{i}", group="nature", features=out, lng=108.44 + i / 1000) for i in range(3)])
    v = run(session(trip(context={"start_date": "2026-10-25", "days": 3})), d, CFG).view
    cards = [c for g in v["groups"] for c in g["cards"]]
    assert [n["code"] for n in v["notes"]] == ["rain"] and "Tháng 10" in v["notes"][0]["text"]
    assert all(c["outdoor"] and not any("mưa" in t["text"] for t in c["tradeoffs"]) for c in cards)
    assert run(session(), d, CFG).view["notes"] == []  # December: not a rainy month


def test_a_tab_with_no_place_reaching_the_bar_has_no_badge_but_keeps_its_ranking():
    d = Data([srec("HILL", group="nature", features=FLAT),
              *[srec(f"C{i}", features={"steep_or_stairs": "absent"}, voices=10 + i, lng=108.44 + i / 1000) for i in range(3)]])
    chill = next(g for g in run(session(), d, CFG).view["groups"] if g["id"] == "chill")
    assert chill["total"] == 3 and not any(c["top"] for c in chill["cards"])
    assert [c["score"] for c in chill["cards"]] == sorted((c["score"] for c in chill["cards"]), reverse=True)
