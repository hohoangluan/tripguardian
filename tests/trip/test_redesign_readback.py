"""Trip redesign part 5: the compact read-back, cancelling a guess, a stale read-back, and the read-back in the view.

Spec R §7; architecture doc §5.7. Ids RB1-RB11. The read-back is the last screen before Lịch trình: one short card the
user reads in seconds, grouped like R §7's sample, never one line per field.
"""

from datetime import date

import pytest
from trip_fixtures import ScriptedChat

from trip import TripState, compile_search_input, plan_digest
from trip.agent import AgentError
from trip.api.engine import Engine, TurnInput
from trip.domain import readback
from trip.domain.state import with_meta
from trip.domain.understanding import view as understanding
from trip.infrastructure.sessions import SessionStore


def said(value, turn=1, source="user", quote="q"):
    return {"value": value, "source": source, "confidence": "high" if source == "user" else "medium",
            "status": "confirmed" if source == "user" else "unknown", "evidence": [{"turn": turn, "quote": quote}]}


FULL = {"start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("14:00"), "checkout_at": said("12:00"),
        "companions": said(["partner"]), "people": said(2), "mobility": said("motorbike"), "care": said("none"),
        "pace": said("slow"), "budget_vnd": said(25_000_000), "budget_scope": said("trip_total"),
        "lodging": said({"text": "Khách sạn Colline", "lat": 11.94, "lng": 108.43, "kind": "address"})}


def build(drop=(), **over):
    data = {k: v for k, v in FULL.items() if k not in drop}
    data.update(over)
    return TripState.model_validate(data)


def lines(st):
    return readback.build(compile_search_input(st)).lines


def everything():
    """Every kind of fact the read-back can carry at once: the worst case for its length."""
    return build(
        days=said(5), checkin_at=said("10:45"),
        companions_other=("bà ngoại",),
        frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"}),
               "leave": said({"at": "2026-11-24T16:00", "how": "plane"}),
               "days": [{"index": 1, "start": "05:00", "source": "user"}, {"index": 2, "intensity": "free", "source": "user"},
                        {"index": 3, "start": "07:00", "source": "user"}],
               "busy": [{"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00", "on": "all"},
                        {"label": "họp online", "kind": "work", "where": "lodging", "start": "09:00", "end": "10:00", "on": [3]}],
               "rest": said({"every_min": 60, "rest_min": 15}),
               "drive_day_min": said(120),
               "periods": [{"period": "morning", "activity": "săn mây"}, {"period": "sunset", "activity": "ngắm hoàng hôn"}]},
        max_leg_min=said(30),
        hard=[{"feature": "steep_or_stairs", "op": "ne", "value": "present", "evidence": [{"turn": 1, "quote": "không leo dốc"}]}],
        soft={"crowd=low": said("love", source="inferred"), "scenic_view=present": said("love"),
              "live_music=present": said("love", source="inferred"), "noise=quiet": said("love", source="inferred"),
              "photo_spot=present": said("love", source="inferred")},
        unmapped=[{"phrase": "quán halal", "turn": 1}, {"phrase": "dị ứng đậu phộng", "turn": 1}],
    )


# ---------- RB1-RB2: short and grouped ----------

def test_rb1_the_worst_case_readback_still_fits_one_card():
    ls = lines(everything())
    assert len(ls) <= 12, [l.text for l in ls]
    assert sum(l.kind == "default" for l in ls) <= 1  # every default in one "Mặc định" line
    assert sum(l.kind == "check" for l in ls) <= 1  # every unchecked wish in one "Tự kiểm" line
    assert sum(l.kind == "guess" for l in ls) <= 3  # more guesses than three fold into the last guess line
    for tab in ("companions", "mobility", "care", "pace", "budget", "lodging"):
        assert sum(l.tab == tab and l.kind == "said" for l in ls) <= 1, tab
    assert sum(l.tab == "trip" and l.kind == "said" for l in ls) <= 2  # dates + hours, then the days that differ


def test_rb1_a_long_trip_does_not_grow_one_line_per_day():
    st = build(days=said(14), frame={"days": [{"index": i, "start": "06:00", "source": "user"} for i in range(1, 14, 2)]})
    ls = lines(st)
    assert len(ls) <= 8, [l.text for l in ls]
    assert not any(l.text.startswith("Ngày 2 bắt đầu") for l in ls)


def test_rb2_the_trip_line_names_weekdays_and_the_physical_reason_for_the_hours():
    st = build(drop=("checkin_at", "checkout_at"),
               frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"}),
                      "leave": said({"at": "2026-11-22T16:00", "how": "plane"})})
    trip = [l.text for l in lines(st) if l.tab == "trip" and l.kind == "said"]
    assert any("T6 20/11 → CN 22/11" in t for t in trip), trip
    head = next(t for t in trip if "T6 20/11" in t)
    assert "9:30" in head and "10:45" in head and "16:00" in head  # arrival, ready time, departure


# ---------- RB3: money the way people say it ----------

@pytest.mark.parametrize("amount, text", [
    (25_000_000, "25 triệu"), (2_500_000, "2,5 triệu"), (1_500_000, "1,5 triệu"), (800_000, "800 nghìn"),
    (1_200_000_000, "1,2 tỷ"), (500, "500 đồng"), (10_000_000, "10 triệu"),
])
def test_rb3_money_reads_in_vietnamese_units(amount, text):
    assert readback.vnd(amount) == text


def test_rb3_the_budget_line_never_prints_raw_digits():
    budget = next(l.text for l in lines(build()) if l.tab == "budget")
    assert "25 triệu" in budget and "cả nhóm" in budget
    assert "25,000,000" not in budget and "25.000.000" not in budget and "25000000" not in budget


# ---------- RB4-RB6: kinds stay honest when lines merge ----------

def test_rb4_defaults_are_never_inside_a_said_line():
    st = build(frame={"days": [{"index": 1, "start": "05:00", "source": "user"}]})
    ls = lines(st)
    said_text = " ".join(l.text for l in ls if l.kind == "said")
    default = next(l for l in ls if l.kind == "default")
    assert "05:00" in said_text
    assert "21:00" not in said_text and "21:00" in default.text  # day 2 ends at the default, said nowhere
    assert "08:00" in default.text  # day 3 starts at the default


def test_rb4_a_free_day_the_user_asked_for_is_said():
    st = build(frame={"days": [{"index": 1, "intensity": "free", "source": "user"}]})
    said_lines = [l for l in lines(st) if l.kind == "said" and l.tab == "trip"]
    assert any("Ngày 2" in l.text and "để trống" in l.text for l in said_lines)


def test_rb5_the_unchecked_best_time_is_said_once_with_the_wishes_without_data():
    ls = lines(everything())
    check = [l for l in ls if l.kind == "check"]
    assert len(check) == 1
    assert check[0].text.count("chưa kiểm được") <= 1
    assert "quán halal" in check[0].text and "dị ứng đậu phộng" in check[0].text


def test_rb6_each_guess_can_be_cancelled_and_said_lines_cannot():
    st = build(soft={"crowd=low": said("love", source="inferred")},
               budget_scope=said("trip_total", source="inferred"))
    ls = lines(st)
    guesses = [l for l in ls if l.kind == "guess"]
    assert guesses and all(l.undo for l in guesses)
    assert {"soft:crowd=low", "budget_scope"} <= {l.undo for l in guesses}
    assert all(l.undo is None for l in ls if l.kind != "guess")


def test_rb6_the_readback_is_deterministic():
    st = everything()
    assert lines(st) == lines(st)
    assert readback.build(compile_search_input(st)).digest == plan_digest(compile_search_input(st))


# ---------- RB7-RB11: the engine and the view ----------

@pytest.fixture
def engine(catalog, cfg, tmp_path):
    chat = ScriptedChat(error=AgentError("the model must not be called for a read-back tap"))
    return Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15)), chat


def seeded(e, st):
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = st
    e.store.save(s)
    return sid


def send(e, sid, **kw):
    events = []
    e.turn(sid, TurnInput(**kw), lambda ev, d: events.append((ev, d)))
    return events


def test_rb7_cancelling_a_guess_removes_only_that_guess_without_the_model(engine):
    e, chat = engine
    sid = seeded(e, build(soft={"crowd=low": said("love", source="inferred"), "scenic_view=present": said("love")}))
    send(e, sid, kind="drop", target="soft:crowd=low")
    st = e.store.get(sid).state
    assert chat.calls == 0
    assert "crowd=low" not in st.soft and "scenic_view=present" in st.soft


def test_rb7_a_users_own_words_cannot_be_cancelled_as_a_guess(engine):
    e, _ = engine
    sid = seeded(e, build(soft={"scenic_view=present": said("love")}))
    for target in ("soft:scenic_view=present", "pace", "budget_scope", "nonsense", ""):
        send(e, sid, kind="drop", target=target)
    st = e.store.get(sid).state
    assert "scenic_view=present" in st.soft and st.pace.value == "slow" and st.budget_scope.value == "trip_total"


def test_rb8_the_view_carries_the_readback_only_when_nothing_is_missing(catalog, cfg):
    assert understanding(build(drop=("pace",)), catalog, cfg)["readback"] is None
    rb = understanding(build(), catalog, cfg)["readback"]
    assert rb["ok"] is False and rb["digest"] == plan_digest(compile_search_input(build()))
    assert rb["lines"] and set(rb["lines"][0]) == {"kind", "text", "tab", "undo"}
    st = with_meta(build(), readback_digest=rb["digest"])
    assert understanding(st, catalog, cfg)["readback"]["ok"] is True


def test_rb9_confirming_a_readback_the_user_did_not_see_is_refused(engine):
    e, _ = engine
    sid = seeded(e, build())
    events = send(e, sid, kind="readback_ok", value="0" * 64)
    assert e.store.get(sid).state.meta.readback_digest is None
    assert any(ev == "readback" for ev, _ in events)  # the fresh read-back, to read again


def test_rb10_confirming_the_digest_seen_stores_it(engine):
    e, _ = engine
    st = build()
    sid = seeded(e, st)
    digest = plan_digest(compile_search_input(st))
    send(e, sid, kind="readback_ok", value=digest)
    assert e.store.get(sid).state.meta.readback_digest == digest


def test_rb11_the_trip_module_reads_back_and_compiles_for_the_harness(catalog, cfg, tmp_path):
    from trip import Tools
    e = Engine(catalog, cfg, SessionStore(None), ScriptedChat(), today=lambda: date(2026, 10, 15))
    tools = Tools(e)
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = build(drop=("pace",))
    e.store.save(s)
    out = tools.read(sid, "readback", {})
    assert out["missing"] == ["pace"] and out["ok"] is False
    assert out["deck"]["kind"] == "deck" and [t["qid"] for t in out["deck"]["tabs"]] == ["pace"]
    s.state = build()
    e.store.save(s)
    out = tools.read(sid, "readback", {})
    assert out["missing"] == [] and out["lines"] and out["digest"]
    si = tools.read(sid, "search_input", {})
    assert si["readiness"] == {"missing": [], "readback_ok": False}
    tools.apply(sid, "turn", {"kind": "readback_ok", "value": out["digest"]}, lambda *_: None)
    assert tools.read(sid, "search_input", {})["readiness"]["readback_ok"] is True
