"""Gate questions ask only what is missing; arrival, diet and allergy are recorded; party clashes are asked."""

from datetime import date

from trip_fixtures import ScriptedChat
from test_redesign_gate import build, said

from trip import TripState
from trip.agent import AgentError
from trip.api.engine import Engine
from trip.domain import derive, readback, required
from trip.domain.prepass import prepass
from trip.domain.questions import HARD_LABEL
from trip.domain.understanding import view
from trip.infrastructure.sessions import SessionStore

TODAY = date(2026, 10, 17)


def tab(state, cfg, qid):
    return next(t for t in required.tabs(state, cfg) if t.qid == qid)


def read(engine, text):
    return engine._deterministic(TripState(), text, prepass(text, TODAY), 1)


def engine(catalog, cfg, tmp_path):
    return Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat(error=AgentError("no model")), today=lambda: TODAY)


# 1. prefilled gate questions
def test_dates_card_repeats_the_length_and_asks_only_the_start(catalog, cfg):
    st = build(drop=("start_date",), days=said(3))
    q = tab(st, cfg, "trip").question
    assert "3 ngày" in q and "từ ngày nào đến ngày nào" not in q and "bắt đầu từ ngày nào" in q


def test_companions_card_does_not_ask_the_count_it_guessed(catalog, cfg):
    st = build(people=said(3, source="inferred"))
    q = tab(st, cfg, "companions").question
    assert "3 người" in q and "tổng cộng mấy người" not in q


def test_mobility_card_names_the_way_in_and_the_guess(catalog, cfg):
    st = build(drop=("mobility",), arrival_mode=said("bus"))
    assert "xe khách" in tab(st, cfg, "mobility").question
    st = build(mobility=said("car", source="inferred"), driver=said("self", source="inferred"))
    assert "ô tô tự lái" in tab(st, cfg, "mobility").question


# 2. arrival
def test_arrival_words_are_recorded_as_how_they_come(catalog, cfg, tmp_path):
    e = engine(catalog, cfg, tmp_path)
    assert read(e, "đi xe khách 3 ngày").arrival_mode.value == "bus"
    st = read(e, "đi máy bay từ Hà Nội")
    assert st.arrival_mode.value == "plane" and st.arrival_mode.source == "user"
    assert read(e, "không đi xe khách").arrival_mode.value is None


def test_self_driven_car_is_arrival_self_and_a_mobility_guess(catalog, cfg, tmp_path):
    st = read(engine(catalog, cfg, tmp_path), "ô tô tự lái từ Sài Gòn")
    assert st.arrival_mode.value == "self" and st.arrival_mode.source == "user"
    assert st.mobility.value == "car" and st.mobility.source != "user"
    assert st.driver.value == "self" and st.driver.source != "user"


# 3. diet and allergy
def test_vegetarian_becomes_a_hard_diet_filter(catalog, cfg, tmp_path):
    e = engine(catalog, cfg, tmp_path)
    st = derive.derive(read(e, "mình ăn chay"), catalog, 1)
    assert any(h.feature == "vegetarian_options" and h.value == "yes" for h in st.hard)
    assert "vegetarian_options" in HARD_LABEL


def test_seafood_allergy_is_kept_as_a_note_and_answers_care(catalog, cfg, tmp_path):
    st = read(engine(catalog, cfg, tmp_path), "mình dị ứng hải sản")
    assert any("hải sản" in u.phrase for u in st.unmapped)
    assert st.care.value == "listed" and st.care.source == "user"


def test_solo_budget_is_one_person(catalog, cfg):
    st = build(drop=("companions", "budget_scope"), companions=said(["solo"]), people=said(1))
    labels = [o.label for o in tab(st, cfg, "budget").options]
    assert "Cho 1 người, cả chuyến" in labels and "Cả nhóm, cả chuyến" not in labels
    assert view(st, catalog_of(catalog), cfg)["budget_vnd"]["solo"] is True


def catalog_of(c):
    return c


# 4. contradiction
def test_solo_with_six_people_is_asked(catalog, cfg):
    assert readback.party_conflict(["solo"], 6)
    assert readback.party_conflict(["partner"], 1)
    assert readback.party_conflict(["partner"], 2) is None
    assert readback.party_conflict(None, 6) is None


def test_readback_blocks_and_asks_when_solo_has_six_people(catalog, cfg, tmp_path):
    e = engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = build(companions=said(["solo"]), people=said(6))
    s.card = None
    e.store.save(s)
    rb = e._readback(e.store.get(sid).state)
    assert rb["ok"] is False and rb["conflicts"]
    assert any(l["kind"] == "check" and "một mình" in l["text"] for l in rb["lines"])
    events = []
    e.turn(sid, __import__("trip.api.engine", fromlist=["TurnInput"]).TurnInput(kind="readback_ok"), lambda a, b: events.append(a))
    assert "readback" in events and e.store.get(sid).state.meta.readback_digest is None


def test_skipped_lodging_counts_as_resolved(catalog, cfg):
    from trip.domain import readiness
    from trip.domain.state import with_meta
    st = build(drop=("lodging",))
    assert [k for k, _ in readiness.missing(st)] == ["lodging"]
    st = with_meta(st, declined=("lodging",))
    assert readiness.missing(st) == []


def test_gate_deck_has_every_missing_topic_including_lodging(catalog, cfg):
    from trip.domain import deck
    st = TripState()
    d = deck.build(st, catalog, cfg, at="gate")
    assert [t.qid for t in d.tabs] == ["trip", "companions", "mobility", "care", "pace", "budget", "lodging"]
    d = deck.build(build(drop=("lodging",)), catalog, cfg, at="gate")
    assert [t.qid for t in d.tabs] == ["lodging"]


def test_skip_tap_on_lodging_ends_the_gate(catalog, cfg, tmp_path):
    from trip.api.engine import TurnInput
    e = engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = build(drop=("lodging",)); s.card = None
    e.store.save(s)
    e.turn(sid, TurnInput(kind="deck", answers={"lodging": ["skip"]}), lambda *_: None)
    from trip.domain import readiness
    assert readiness.missing(e.store.get(sid).state) == []
