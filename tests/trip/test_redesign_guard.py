"""Trip redesign part 1: nothing the user says is lost, nothing unsaid is written.

Adversarial cases from docs/superpowers/specs/2026-10-15-trip-understanding-cases.md §3 (77 personas run on the real
model); test ids G1-G14 of docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md §5.1.
"""

from datetime import date

import pytest
from trip_fixtures import ScriptedChat, fact, reply, say

from trip import compile_search_input
from trip.domain.dates import exact_date
from trip.domain.guard import bad_say, record_fact
from trip.domain.prepass import prepass
from trip.domain.state import TripState

TODAY = date(2026, 10, 15)  # a Thursday


def put(state, field, value, quote, text, catalog, op="set", how="said", turn=1, history=(), requirement=None):
    return record_fact(state, field, op, value, quote, how, text, turn, catalog, requirement=requirement,
                       history=history)


# ---------- G1-G3: who goes ----------

@pytest.mark.parametrize("text, quote", [
    ("đi Đà Lạt với bồ 3 ngày", "bồ"),
    ("dl 2n1đ với ny", "ny"),
    ("đi với ngừi iu nha", "ngừi iu"),
    ("mình và vợ đi nghỉ", "vợ"),
    ("me and my wife, 3 days", "wife"),
    ("đi cùng chồng", "chồng"),
])
def test_g1_every_way_to_name_a_partner_is_heard(catalog, text, quote):
    st, note = put(TripState(), "companions", "partner", quote, text, catalog, op="add")
    assert note == "" and "partner" in st.companions.value


@pytest.mark.parametrize("text, quote, value", [
    ("đi với mẹ", "với mẹ", "parents"),
    ("dẫn ba má đi chơi", "ba má", "parents"),
    ("đi với bé 6 tuổi", "bé 6 tuổi", "kids"),
    ("2 bé 8 và 11 tuổi", "2 bé 8 và 11 tuổi", "kids"),
    ("tụi tui 4 đứa bạn", "4 đứa bạn", "friends"),
    ("5 đứa sinh viên", "5 đứa sinh viên", "friends"),
    ("đi với 2 đứa bạn thân", "2 đứa bạn thân", "friends"),
])
def test_g2_family_and_friends_in_everyday_words_are_heard(catalog, text, quote, value):
    st, note = put(TripState(), "companions", value, quote, text, catalog, op="add")
    assert note == "" and value in st.companions.value


@pytest.mark.parametrize("text, quote", [("đi cả nhà", "cả nhà"), ("đi với họ hàng", "họ hàng")])
def test_g3_a_group_with_no_id_is_kept_never_lost_and_still_asked(catalog, text, quote):
    from trip.domain import readiness
    st, note = put(TripState(), "companions", quote, quote, text, catalog, op="add")
    kept = quote in st.companions_other or any(u.phrase == quote for u in st.unmapped)
    assert kept and not note.startswith("refused")
    assert "companions" in [k for k, _ in readiness.missing(st)]  # still answered on tab ②, prefilled


def test_g1_a_group_the_words_do_not_name_is_still_never_written_as_said(catalog):
    # open vocabulary must not mean "anything goes": "hàng xóm" is not a partner
    st, _ = put(TripState(), "companions", "partner", "hàng xóm", "đi với hàng xóm", catalog, op="add")
    assert not (st.companions.known and st.companions.source == "user" and "partner" in st.companions.value)


# ---------- G4: wrong metadata drops the metadata, never the fact ----------

@pytest.mark.parametrize("requirement", [{"subject_count": 99}, {"no_such_key": 1}, {"scope": "not_a_scope"}])
def test_g4_malformed_requirement_metadata_keeps_the_soft_fact(catalog, requirement):
    st, note = put(TripState(), "soft", "noise=quiet:love", "yên tĩnh", "thích chỗ yên tĩnh", catalog, op="add",
                   requirement=requirement)
    assert "noise=quiet" in st.soft and st.soft["noise=quiet"].requirement is None
    assert note.startswith("warning")


def test_g4_a_wrong_scope_on_a_hard_access_limit_keeps_it_everywhere(catalog):
    # dropping a wrong scope makes the limit apply to every visit: stricter, never hidden (fail-closed)
    st, note = put(TripState(), "hard", "steep_or_stairs!=present", "không leo dốc", "không leo dốc", catalog,
                   op="add", requirement={"meaning": "không leo dốc", "scope": "eating", "subject": "traveler"})
    assert note.startswith("warning")
    assert [(h.feature, h.scope) for h in st.hard] in ([("steep_or_stairs", None)], [("steep_or_stairs", "all")])


def test_g4_an_unresolved_ambiguity_is_still_refused_for_a_hard_limit(catalog):
    st, note = put(TripState(), "hard", "vegetarian_options=yes", "chay", "chay", catalog, op="add", how="inferred",
                   requirement={"meaning": "vegetarian meal options", "scope": "eating", "subject": "unspecified",
                                "ambiguity": "diet or preference"})
    assert note.startswith("refused") and not st.hard


# ---------- G5-G6: a quote from an earlier turn ----------

def test_g5_a_fact_said_in_an_earlier_turn_is_recorded_with_that_turn(catalog):
    history = ((1, "mình ăn chay nha"), (2, "đi 3 ngày"))
    st, note = put(TripState(), "signal", "vegetarian", "ăn chay", "ok bạn", catalog, op="add", turn=3,
                   history=history)
    assert note == ""
    assert [(s.kind, s.turn) for s in st.signals] == [("vegetarian", 1)]


def test_g6_a_quote_from_no_turn_at_all_is_still_refused(catalog):
    st, note = put(TripState(), "days", "3", "3 ngày", "ok bạn", catalog, turn=3, history=((1, "đi với bồ"),))
    assert note.startswith("refused") and not st.days.known


def test_g5_the_engine_hands_earlier_turns_to_the_guard(catalog, cfg, tmp_path):
    from trip.api.engine import Engine, TurnInput
    from trip.infrastructure.sessions import SessionStore
    chat = ScriptedChat(say("Bạn đi mấy ngày?"), reply(fact("mobility", "motorbike", "xe máy")), say(""))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="mình đi xe máy nhé"), lambda *_: None)
    e.turn(sid, TurnInput(kind="text", text="ok"), lambda *_: None)
    s = e.store.get(sid)
    said_at = next(t["turn"] for t in s.transcript if t["role"] == "user" and "xe máy" in t["text"])
    assert s.state.mobility.value == "motorbike" and s.state.mobility.evidence[0].turn == said_at


# ---------- G7: taking a companion back takes back what was read from it ----------

def test_g7_removing_parents_removes_the_elderly_signal_read_from_them(catalog):
    text = "đi với bố mẹ"
    st, _ = put(TripState(), "companions", "parents", "bố mẹ", text, catalog, op="add")
    st, _ = put(st, "signal", "elderly", "bố mẹ", text, catalog, op="add", how="inferred")
    assert [s.kind for s in st.signals] == ["elderly"]
    st, _ = put(st, "companions", "parents", "không đi với bố mẹ nữa", "thôi không đi với bố mẹ nữa", catalog,
                op="remove", turn=2)
    assert not st.signals


def test_g7_a_signal_with_its_own_words_stays_when_the_companion_goes(catalog):
    text = "đi với bố mẹ, bà bị đau gối"
    st, _ = put(TripState(), "companions", "parents", "bố mẹ", text, catalog, op="add")
    st, _ = put(st, "signal", "elderly", "bố mẹ", text, catalog, op="add", how="inferred")
    st, _ = put(st, "signal", "knee", "đau gối", text, catalog, op="add")
    st, _ = put(st, "companions", "parents", "bỏ bố mẹ", "bỏ bố mẹ ra", catalog, op="remove", turn=2)
    assert [s.kind for s in st.signals] == ["knee"]


# ---------- G8-G9: how the trip moves around ----------

@pytest.mark.parametrize("text, quote, value", [
    ("đi Grab cho tiện", "Grab", "car"), ("đi taxi", "taxi", "car"), ("thuê xe có tài xế", "xe có tài xế", "car"),
    ("đi Grab cho tiện", "Grab", "grab"), ("đi taxi", "taxi", "taxi"),
])
def test_g8_a_hired_ride_is_a_car_with_a_hired_driver(catalog, text, quote, value):
    st, note = put(TripState(), "mobility", value, quote, text, catalog)
    assert note == "" and st.mobility.value == "car" and st.driver.value == "hired"
    assert compile_search_input(st).context.driver == "hired"


def test_g8_own_car_is_driven_by_the_party(catalog):
    st, _ = put(TripState(), "mobility", "car", "tự lái", "tự lái ô tô lên", catalog)
    assert st.mobility.value == "car" and st.driver.value != "hired"


@pytest.mark.parametrize("value", ["walk", "walking"])
def test_g9_walking_is_a_way_to_move(catalog, value):
    st, note = put(TripState(), "mobility", value, "đi bộ là chính", "mình đi bộ là chính", catalog)
    assert note == "" and st.mobility.value == "walk"


# ---------- G10: relative dates become dates, by code ----------

@pytest.mark.parametrize("expression, expected", [
    ("Tết dương lịch", date(2027, 1, 1)),
    ("chủ nhật này", date(2026, 10, 18)),
    ("cuối tuần này", date(2026, 10, 17)),
    ("cuối tuần sau", date(2026, 10, 24)),
    ("thứ 6 tuần sau", date(2026, 10, 23)),
    ("lễ 30/4", date(2027, 4, 30)),
])
def test_g10_resolver_knows_the_phrases_users_type(expression, expected):
    assert exact_date(expression, TODAY) == expected


@pytest.mark.parametrize("text, expected", [
    ("đi Đà Lạt cuối tuần này 2 ngày", date(2026, 10, 17)),
    ("tết dương lịch đi dl 3n2đ", date(2027, 1, 1)),
    ("thứ 6 tuần sau đi 3 ngày", date(2026, 10, 23)),
])
def test_g10_prepass_writes_the_date_without_waiting_for_the_model(text, expected):
    starts = [p.value for p in prepass(text, TODAY).proposals if p.field == "start_date"]
    assert starts == [expected]


def test_g10_a_vague_week_is_not_turned_into_a_made_up_day():
    assert [p for p in prepass("tuần sau đi", TODAY).proposals if p.field == "start_date"] == []


# ---------- G11: the reply never shows internals ----------

@pytest.mark.parametrize("say_text", [
    "Mình đã ghi lại (budget_scope, people) rồi nhé.",
    "Mình ghi nhận signal sức khỏe của bạn.",
    "Đã lưu crowd_tolerance = avoid.",
])
def test_g11_field_ids_never_reach_the_user(catalog, say_text):
    assert bad_say(say_text, "đi 2 người", TripState(), catalog, set()) is not None


# ---------- G12: a contradiction is asked, not silently resolved ----------

def test_g12_two_paces_in_one_message_keep_neither_and_flag_the_conflict(catalog):
    text = "muốn đi nhiều chỗ nhưng thong thả thôi"
    st, _ = put(TripState(), "pace", "packed", "đi nhiều chỗ", text, catalog)
    st, note = put(st, "pace", "slow", "thong thả", text, catalog)
    assert not st.pace.known and "pace" in st.meta.conflicts
    assert not note.startswith("refused")  # the agent is told, the user gets a choice, nothing is lost


def test_g12_a_later_turn_changing_pace_is_a_change_of_mind_not_a_conflict(catalog):
    st, _ = put(TripState(), "pace", "packed", "đi nhiều chỗ", "đi nhiều chỗ", catalog, turn=1)
    st, _ = put(st, "pace", "slow", "thôi thong thả", "thôi thong thả", catalog, turn=2)
    assert st.pace.value == "slow" and "pace" not in st.meta.conflicts


# ---------- G13: a daily driving limit is not a per-leg limit ----------

def test_g13_daily_driving_cap_goes_to_the_frame(catalog):
    text = "lái tối đa 2 tiếng mỗi ngày"
    st, note = put(TripState(), "drive_day_min", "120", "tối đa 2 tiếng mỗi ngày", text, catalog)
    assert note == "" and st.frame.drive_day_min.value == 120 and not st.max_leg_min.known


# ---------- G14: a vague lodging word never becomes some random place ----------

def test_g14_a_vague_word_never_resolves_to_a_place(catalog):
    st, _ = put(TripState(), "base", "dorm", "dorm", "ở dorm cho rẻ", catalog)
    assert not (st.base.known and st.base.value.place_id)
