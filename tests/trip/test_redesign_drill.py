"""Trip redesign part 4: drill a broad taste down with three real photos; the remedy ladder for unusual wishes.

Spec R §9, §11; architecture doc §5.6. Ids D1-D7 (drill), L1-L6 (ladder). The photo index is faked with fixed scores
so the selection rule is tested exactly; the real index is measured by the persona bench.
"""

import json
from datetime import date

import pytest
from trip_fixtures import rec

from trip import Catalog, TripState, compile_search_input
from trip.domain import deck, drill
from trip.domain.prepass import prepass

TODAY = date(2026, 10, 15)


def said(value, source="user", quote="q"):
    return {"value": value, "source": source, "confidence": "high", "status": "confirmed",
            "evidence": [{"turn": 1, "quote": quote}]}


@pytest.fixture
def big():
    """60 cloud-hunting places, 6 cafes with menus, 2 karaoke bars, one named reference place."""
    out = [rec(i, f"Đồi Mây {i}", {"cloud_hunting": ("present", 5), "scenic_view": ("present", 4)}) for i in range(1, 61)]
    for i in range(61, 67):
        r = rec(i, f"Quán Bánh Căn {i}", {"food_quality": ("good", 5)})
        r["identity"]["category"] = "Quán ăn"
        r["menu"] = {"dishes": [{"name": "Bánh căn trứng", "popular": i == 61}]}
        out.append(r)
    for i in (67, 68):
        r = rec(i, f"Karaoke Sao {i}", {"live_music": ("present", 3)})
        r["identity"]["category"] = "Karaoke"
        out.append(r)
    out.append(rec(69, "Túi Mơ To", {"crowd": ("high", 9), "scenic_view": ("present", 9)}))
    return Catalog.from_records(out, n_min=1)


class FakeLooks:
    """scored_by_cues(cues, within) -> [(place_id, best photo score)], best first; fixed per first cue."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def ready(self, wait_s=0.0):
        return True

    def scored_by_cues(self, cues, within=None):
        self.calls.append((tuple(cues), within))
        return [(p, s) for p, s in self.table.get(cues[0], []) if within is None or p in within]

    def best_photo(self, pid):
        return f"gmaps/places/{pid}/best.jpg"


def ids(a, b):
    return [f"0x{i:x}:0x1" for i in range(a, b)]


def variant(label, cue, axis="place"):
    return {"label": label, "cues": [cue, "x", "y"], "axis": axis,
            "writes": [{"field": "soft", "op": "add", "value": "scenic_view=present:love"}]}


# ---------- D1-D2: which tastes are drilled ----------

def test_d1_broad_tastes_are_found_in_the_order_said():
    assert drill.topics("đi săn mây, ngồi cà phê, tối đi ăn uống") == ["săn mây", "cà phê", "ăn uống"]


def test_d1_a_taste_already_specific_is_not_drilled():
    assert "cà phê" not in drill.topics("thích cà phê vintage có nhiều sách cũ")


def test_d2_at_most_three_tastes_are_drilled_per_trip():
    text = "săn mây, ngắm đồi, cà phê, chụp ảnh, cắm trại"
    assert len(drill.topics(text)) == 5
    st = drill.note(TripState(), text, turn=1)
    assert [d.topic for d in st.drills if d.status == "pending"] == ["săn mây", "ngắm đồi", "cà phê"]


# ---------- D3-D5: the three photos ----------

def test_d3_code_keeps_the_three_variants_with_most_places_times_best_photo(big, cfg):
    table = {
        "sương": [(p, 0.20) for p in ids(1, 31)],          # 30 x .20 = 6.0
        "trời trong": [(p, 0.30) for p in ids(31, 43)],    # 12 x .30 = 3.6
        "hoàng hôn": [(p, 0.15) for p in ids(1, 51)],      # 50 x .15 = 7.5, same top place as "sương"
        "bình minh": [(p, 0.50) for p in ids(51, 59)],     # 8 places: below drill_min
        "mây chùa": [(p, 0.12) for p in ids(1, 41)],       # best photo below drill_score_min (wrong kind of place)
    }
    looks = FakeLooks(table)
    vs = [variant("Sương sớm", "sương"), variant("Trời trong", "trời trong"), variant("Hoàng hôn", "hoàng hôn"),
          variant("Bình minh", "bình minh"), variant("Mây trên chùa", "mây chùa")]
    opts = drill.choose(vs, "săn mây", TripState(), big, looks, cfg)
    assert [o.label for o in opts] == ["Hoàng hôn", "Sương sớm", "Trời trong"]
    reps = [o.photo[0] for o in opts]
    assert len(set(reps)) == 3  # each photo shows a different place
    assert all(o.count >= 10 for o in opts)
    assert all(within and within <= set(big.by_id) for _, within in looks.calls)  # only the taste's real places


def test_d4_fewer_than_two_good_variants_means_no_photo_tab(big, cfg):
    looks = FakeLooks({"sương": [(p, 0.2) for p in ids(1, 31)], "bình minh": [(p, 0.5) for p in ids(51, 55)]})
    assert drill.choose([variant("Sương", "sương"), variant("Bình minh", "bình minh")], "săn mây", TripState(), big,
                        looks, cfg) == []


def test_d5_a_time_of_day_variant_writes_a_period_and_the_readback_admits_no_best_time(big, cfg):
    from trip.domain import readback
    looks = FakeLooks({"sáng": [(p, 0.2) for p in ids(1, 31)], "chiều": [(p, 0.2) for p in ids(11, 41)]})
    vs = [dict(variant("Buổi sáng", "sáng", axis="time"), period="morning"),
          dict(variant("Buổi chiều", "chiều", axis="time"), period="afternoon")]
    opts = drill.choose(vs, "săn mây", TripState(), big, looks, cfg)
    morning = next(o for o in opts if o.label == "Buổi sáng")
    assert any(w.field == "frame.periods" for w in morning.writes)
    from trip.domain.state import apply_drafts
    st = apply_drafts(TripState.model_validate({"start_date": said("2026-11-20"), "days": said(2)}), morning.writes, 2,
                      tool="deck:drill")
    text = " ".join(l.text for l in readback.build(compile_search_input(st)).lines)
    assert "chưa kiểm được" in text


# ---------- D6-D7: drill in the deck ----------

def test_d6_a_pending_drill_comes_before_confirm_questions_and_a_skip_is_final(big, cfg):
    st = TripState.model_validate({"drills": [{"topic": "săn mây", "quote": "săn mây", "turn": 1, "status": "pending",
                                               "tab": {"qid": "drill.săn mây", "kind": "drill", "header": "Săn mây",
                                                       "question": "Săn mây kiểu nào?", "why": "", "multi": True,
                                                       "inputs": [], "options": []}}],
                                   "soft": {"cloud_hunting=present": said("love", quote="săn mây")}})
    kinds = [t.kind for t in deck.build(st, big, cfg).tabs]
    assert "drill" in kinds and (("confirm" not in kinds) or kinds.index("drill") < kinds.index("confirm"))
    skipped = drill.skip(st, "săn mây")
    assert [d.status for d in skipped.drills] == ["skipped"]
    assert "drill" not in [t.kind for t in deck.build(skipped, big, cfg).tabs]


def test_d7_new_directions_wait_until_no_drill_is_pending():
    from trip.agent.tools import TurnTools
    pending = TripState.model_validate({"drills": [{"topic": "cà phê", "quote": "cà phê", "turn": 1,
                                                    "status": "pending"}]})
    done = TripState.model_validate({"drills": [{"topic": "cà phê", "quote": "cà phê", "turn": 1, "status": "done"}]})
    tools = lambda st: TurnTools(st, "x", 2, Catalog(()), TODAY)  # noqa: E731
    # the tool list stays the same turn to turn (prompt cache); a pending drill refuses the call instead
    assert tools(pending).tool_names() == tools(done).tool_names()
    assert "error" in tools(pending).run("suggest_directions", {})
    assert "directions" in tools(done).run("suggest_directions", {})


# ---------- L1-L6: the remedy ladder ----------

def test_l1_a_dish_finds_the_places_that_serve_it(big):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "muốn ăn bánh căn", 1, big, TODAY)
    out = t.run("record_fact", {"facts": [{"field": "dish", "op": "add", "value": "bánh căn", "quote": "bánh căn", "how": "said"}]})["results"][0]
    assert out["count"] == 6 and "0x3d:0x1" == out["top"][0]["id"]  # the owner's popular dish first
    assert [w.dish for w in t.state.wishes.dishes] == ["bánh căn"]
    assert compile_search_input(t.state).wishes.dishes[0].dish == "bánh căn"


def test_l2_a_kind_of_place_finds_its_category(big):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "tối đi hát karaoke", 1, big, TODAY)
    out = t.run("record_fact", {"facts": [{"field": "kind", "op": "add", "value": "karaoke", "quote": "karaoke", "how": "said"}]})["results"][0]
    assert out["count"] == 2 and [w.kind for w in t.state.wishes.kinds] == ["karaoke"]


def test_l3_like_a_place_but_quieter_is_a_reference_not_a_must_go(big):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "muốn chỗ giống Túi Mơ To nhưng vắng hơn", 1, big, TODAY)
    t.run("record_fact", {"field": "like", "op": "add", "how": "said", "quote": "giống Túi Mơ To nhưng vắng hơn",
                          "value": json.dumps({"place": "Túi Mơ To", "but": ["crowd=low"]})})
    (like,) = t.state.wishes.like
    assert like.place_id == "0x45:0x1" and like.but == ("crowd=low",)
    assert not t.state.anchors and not t.state.hard


def test_l4_a_wish_with_no_data_is_said_kept_and_counted_for_offline(big, tmp_path):
    from trip.agent.tools import TurnTools
    gaps = tmp_path / "gaps.jsonl"
    for turn in (1, 2):
        t = TurnTools(TripState(), "cần quán halal", turn, big, TODAY, gaps=gaps)
        t.run("record_fact", {"field": "unmapped", "op": "add", "how": "said", "quote": "quán halal",
                              "value": "quán halal", "gap": "no_data"})
    rows = [json.loads(x) for x in gaps.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["phrase"] == "quán halal" and rows[0]["count"] == 2
    assert rows[0]["kind"] == "no_data" and rows[0]["last_seen"]


def test_l5_gaps_are_the_only_file_online_writes_and_never_place_data(big, tmp_path):
    from trip.agent.tools import TurnTools
    before = {p for p in tmp_path.rglob("*")}
    t = TurnTools(TripState(), "cần bồn tắm", 1, big, TODAY, gaps=tmp_path / "gaps.jsonl")
    t.run("record_fact", {"field": "unmapped", "op": "add", "how": "said", "quote": "bồn tắm", "value": "bồn tắm",
                          "gap": "no_data"})
    assert {p for p in tmp_path.rglob("*")} - before == {tmp_path / "gaps.jsonl"}


def test_l6_lodging_has_no_photos_to_drill_so_it_is_a_gap_not_a_tab(big, cfg, tmp_path):
    assert drill.topics("tìm homestay đẹp") == []  # lodging is never drilled with photos (3/1475 have photos)


def test_l1_prepass_never_writes_a_dish_as_a_place_to_go():
    p = prepass("muốn ăn bánh căn với lẩu gà lá é", TODAY)
    assert not any(x.field == "anchor" for x in p.proposals)
