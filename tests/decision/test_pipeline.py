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
        srec("MEAL", group="restaurant", usable=("meal",), features={"steep_or_stairs": "absent"}),
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


def test_lodging_never_reaches_explore():
    hotel = srec("HOTEL", group="stay", category="Khách sạn", usable=(), features={"scenic_view": "present"})
    s = session(trip(anchors=[{"place_id": "HOTEL", "priority": "must"}]), State(selected=["HOTEL"]))
    v = run(s, Data([*data().records, hotel]), CFG).view
    shown = {c["id"] for g in v["groups"] for c in g["cards"] if c["id"] == "HOTEL"}
    assert not shown and "HOTEL" not in v["shortlist"]


def test_every_card_of_every_group_has_a_reason():  # D5
    from gen import records, sessions
    for seed in range(5):
        recs = records(seed)
        d = Data(recs)
        for s in sessions(seed, recs, 6):
            v = run(s, d, CFG).view
            cards = [c for g in v["groups"] for c in g["cards"]] + v["unverified"]["cards"]
            assert all(len(c["why"]) >= 1 for c in cards), s.id


def _meals(n):
    return [srec(f"M{i:02d}", group="restaurant", category="Nhà hàng", usable=("meal",)) for i in range(n)]


def _session(search):
    return Session(id="0" * 12, search_input=search, state=State())


def _dish_wish(*ids):
    return {"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": list(ids)}], "kinds": [], "like": []}


def test_why_not_names_the_unmet_wish_and_never_says_not_sold():  # D6, D7
    import dataclasses
    recs = _meals(8)
    cfg = dataclasses.replace(CFG, page_size=3)
    search = si(wishes=_dish_wish("M07"))
    res = run(_session(search), Data(recs), cfg)
    out = why_not(res, "M05", search, cfg)  # below the 3-place window (M07, M00, M01)
    assert out["listed"] and any("xếp thứ" in r for r in out["reasons"])
    assert "Chưa thấy ghi món bánh căn ở nơi này" in out["reasons"]
    assert not any("không bán" in r for r in out["reasons"])


def test_why_not_puts_a_hard_fail_before_any_wish():  # D8
    from fixtures import feat
    recs = _meals(3)
    recs[0]["service"]["vegetarian_options"] = feat("no", n=5)
    search = si(hard_filters=[hard("vegetarian_options", "yes", op="eq")], wishes=_dish_wish("M00"))
    out = why_not(run(_session(search), Data(recs), CFG), "M00", search, CFG)
    assert out["reasons"][0].startswith("Bị loại") and not any("mong muốn" in r or "món" in r for r in out["reasons"])


def test_reasons_name_only_what_the_trip_or_record_holds():  # D9
    recs = _meals(4)
    search = si(wishes=_dish_wish("M03"))
    res = run(_session(search), Data(recs), CFG)
    texts = [w["text"] for g in res.view["groups"] for c in g["cards"] for w in c["why"]]
    texts += [r for pid in ("M00", "M01") for r in why_not(res, pid, search, CFG)["reasons"]]
    for t in texts:
        if "món" in t or "bạn muốn" in t:
            assert "bánh căn" in t


def test_a_place_without_a_record_gets_no_wish_and_no_wish_reason():  # final review I2
    search = si(anchors=[{"place_id": "GONE", "priority": "must"}], liked_groups=["sights"],
                context={"purpose": "explore"},
                wishes={"dishes": [], "kinds": [{"kind": "view", "quote": "view", "place_ids": ["GONE"]}], "like": []})
    res = run(_session(search), Data(_meals(2)), CFG)
    gone = res.cands["GONE"]
    assert gone.parts["wish"] == 0.0 and gone.wishes == []
    texts = [w["text"] for w in res.view["groups"][0]["cards"][0]["why"]]
    assert not any("Vì bạn thích" in t or "Hợp chuyến" in t or "Đúng loại" in t for t in texts)


def test_memo_hit_does_not_search_menus_again(monkeypatch):  # final review I3
    from decision import cards
    recs = _meals(4)
    for r in recs:
        r["menu"] = {"dishes": [{"name": "bánh căn", "name_en": None, "section": None, "popular": False, "price": None}],
                     "photos": []}
    s = _session(si(wishes=_dish_wish(*[r["id"] for r in recs])))
    d, memo = Data(recs), {}
    run(s, d, CFG, memo)
    calls = []
    real = cards.dishes.search
    monkeypatch.setattr(cards.dishes, "search", lambda *a, **k: calls.append(1) or real(*a, **k))
    run(s, d, CFG, memo)
    assert calls == []


def test_why_not_tells_a_cafe_it_does_not_list_the_wished_dish():  # user ruling (b): a dish counts wherever it is listed
    cafes = [srec(f"C{i}", group="cafe", usable=("experience",)) for i in range(3)]
    search = si(wishes=_dish_wish("C2"))  # another café lists the dish
    import dataclasses
    cfg = dataclasses.replace(CFG, page_size=1)  # C1 sits below the window, so why_not explains its rank
    res = run(_session(search), Data(cafes), cfg)
    out = why_not(res, "C1", search, cfg)
    assert any("xếp thứ" in r for r in out["reasons"]) and "Chưa thấy ghi món bánh căn ở nơi này" in out["reasons"]


def test_why_not_does_not_tell_the_reference_it_is_unlike_itself():  # final review M1
    from fixtures import feat
    kind = {f: feat("present", n=5) for f in ("scenic_view", "photo_spot", "cozy_decor", "live_music")}
    recs = [srec(p, group="cafe", usable=("experience",), features=kind) for p in ("X", "Y", "Z")]
    search = si(wishes={"dishes": [], "kinds": [], "like": [{"place_id": "X", "but": [], "quote": "giống X"}]})
    import dataclasses
    cfg = dataclasses.replace(CFG, page_size=1)
    res = run(_session(search), Data(recs), cfg)
    assert not any("mong muốn" in r for r in why_not(res, "X", search, cfg)["reasons"])
