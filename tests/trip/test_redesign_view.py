"""Trip redesign part 5c: the understanding view says what the new Hiểu chuyến board reads.

The board (web/src/user/screens/understand/Board.tsx) counts the seven required answers of the gate and shows the
day's hours. V1: arrival and departure live in `frame.arrive` / `frame.leave` since part 1 and never reached the view.
V2: every required key has its group, done or not, so the board and the gate at "Lập lịch" can never disagree.
"""

from trip import TripState
from trip.domain.understanding import view

REQUIRED = ["trip", "companions", "mobility", "care", "pace", "budget", "lodging"]


def said(value, source="user"):
    return {"value": value, "source": source, "confidence": "high", "status": "confirmed",
            "evidence": [{"turn": 1, "quote": "q"}]}


def rows(u):
    return {r["target"]: r for r in u["trip"]}


def test_v1_arrival_and_departure_reach_the_view(catalog, cfg):
    st = TripState.model_validate({"start_date": said("2026-11-20"), "days": said(3),
                                   "frame": {"arrive": said({"at": "2026-11-20T09:30", "how": "plane"}),
                                             "leave": said({"at": "2026-11-22T16:00", "how": "bus"}, "inferred")}})
    r = rows(view(st, catalog, cfg))
    assert r["arrive"]["value"] == {"at": "2026-11-20T09:30", "how": "plane"} and r["arrive"]["mark"] is False
    assert r["leave"]["value"]["how"] == "bus" and r["leave"]["mark"] is True  # a guess is marked ✎


def test_v1_no_arrival_no_row(catalog, cfg):
    assert "arrive" not in rows(view(TripState(), catalog, cfg))


def test_v2_the_view_lists_every_required_group_with_its_state(catalog, cfg):
    u = view(TripState.model_validate({"mobility": said("motorbike"), "pace": said("slow", "inferred")}), catalog, cfg)
    req = u["required"]
    assert [g["key"] for g in req] == REQUIRED
    assert all(g["label"] and "_" not in g["label"] for g in req)
    done = {g["key"]: g["done"] for g in req}
    assert done["mobility"] is True and done["pace"] is False  # a guess is not an answer (A3)
    assert [m["target"] for m in u["missing"]] == [g["key"] for g in req if not g["done"]]


def test_v1_default_moments_are_marked_as_not_said(catalog, cfg):
    st = TripState.model_validate({"frame": {
        "arrive": said({"at": "2026-11-20T09:30", "how": "plane"}, "default"),
        "leave": said({"at": "2026-11-22T16:00", "how": "bus"}, "profile"),
    }})
    result = rows(view(st, catalog, cfg))
    assert result["arrive"]["mark"] is True
    assert result["leave"]["mark"] is True


def test_partial_board_can_display_existing_care_driver_and_budget_answers(catalog, cfg):
    st = TripState.model_validate({"care": said("none"), "driver": said("hired"),
                                   "budget_unlimited": said(True)})
    u = view(st, catalog, cfg)
    r = rows(u)
    assert r["care"]["value"] == "none"
    assert r["driver"]["value"] == "hired"
    assert r["budget_unlimited"]["value"] is True
    assert u["readback"] is None


def test_v3_each_required_group_has_the_designs_short_name(catalog, cfg):
    req = view(TripState(), catalog, cfg)["required"]
    # the old Web design's names: short nouns, not spoken phrases ("Phương tiện", never "cách đi lại")
    assert [g["title"] for g in req] == ["Ngày đi", "Đi với", "Phương tiện", "Lưu ý", "Nhịp độ", "Ngân sách", "Nơi lưu trú"]
    assert all(len(g["title"]) <= 12 for g in req) and all("cách" not in g["label"] for g in req)


def test_v3_deck_tabs_use_the_same_names_as_the_board(catalog, cfg):
    from trip.domain import deck
    tabs = deck.build(TripState(), catalog, cfg, at="gate").tabs
    names = {g["key"]: g["title"] for g in view(TripState(), catalog, cfg)["required"]}
    assert tabs and all(t.header == names[t.qid] for t in tabs if t.kind == "required")
