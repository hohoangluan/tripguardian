"""Long-term pattern learning and the idle stop rule (docs/TRIP_UNDERSTANDING.md §7, §11)."""

from datetime import date, timedelta

import pytest
from trip_fixtures import FakeAgent

from trip.agent import AgentError
from trip.engine import Engine, TurnInput
from trip.patterns import Summary, detect, seed, votes_from_state
from trip.profile import ProfileStore
from trip.questions import prior_q
from trip.sessions import SessionStore
from trip.settings import PatternSettings
from trip.state import Evidence, TripState, Update, apply, settle, with_meta

TODAY = date(2026, 10, 2)
PCFG = PatternSettings(enabled=True, min_sessions=3, window=8, agreement=0.75, stale_days=365, max_places=2)
UID = "user-abc-123"


def vote(sid, day, **votes):
    return Summary(sid=sid, day=day, votes={k.replace("__", ":").replace("_eq_", "="): v for k, v in votes.items()})


def hist(key, values, start=date(2026, 6, 1)):
    return [Summary(sid=f"s{i}", day=start + timedelta(days=i), votes={key: v}) for i, v in enumerate(values)]


# ---------- detect ----------

def test_same_choice_in_enough_sessions_is_a_pattern():
    (p,) = detect(hist("pace", ["slow"] * 3), PCFG, TODAY)
    assert (p.key, p.value, p.sessions, p.confidence) == ("pace", "slow", 3, "medium")


def test_too_few_sessions_is_no_pattern():
    assert detect(hist("pace", ["slow"] * 2), PCFG, TODAY) == []


def test_six_sessions_make_a_high_confidence_pattern():
    assert detect(hist("pace", ["slow"] * 6), PCFG, TODAY)[0].confidence == "high"


def test_a_recent_opposite_choice_ends_the_pattern():
    assert detect(hist("pace", ["slow", "slow", "slow", "packed"]), PCFG, TODAY) == []


def test_mixed_history_below_agreement_is_no_pattern():
    assert detect(hist("pace", ["slow", "packed", "slow", "packed", "slow"]), PCFG, TODAY) == []


def test_old_votes_outside_the_window_do_not_count():
    values = ["packed"] * 5 + ["slow"] * 8
    assert [p.value for p in detect(hist("pace", values), PCFG, TODAY)] == ["slow"]


def test_stale_pattern_is_dropped():
    assert detect(hist("pace", ["slow"] * 3, start=TODAY - timedelta(days=500)), PCFG, TODAY) == []


# ---------- votes ----------

def put(state, field, value, source="user", tool=None, op="set"):
    ev = Evidence(turn=1, tool=tool) if tool else Evidence(turn=1, quote="x")
    return apply(state, Update(field=field, op=op, value=value, source=source, confidence="high", evidence=ev))


def test_votes_are_only_explicit_choices():
    s = put(TripState(), "pace", "slow")
    s = put(s, "soft", ("crowd=low", "avoid"), op="add")
    s = put(s, "soft", ("scenic_view=present", "love"), source="inferred", op="add")  # a guess
    s = put(s, "signal", "knee", op="add")                                           # body: never voted on
    s = put(s, "hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, op="add")
    s = put(s, "days", 3)
    assert votes_from_state(s) == {"pace": "slow", "soft:crowd=low": "avoid"}


def test_a_confirmed_stored_pattern_is_not_a_new_vote(catalog):
    s = seed(TripState(), detect(hist("pace", ["slow"] * 3), PCFG, TODAY), catalog, PCFG)
    assert s.pace.source == "profile"
    kept = put(s, "pace", "slow", tool="chip:prior:keep")
    assert votes_from_state(kept) == {}
    again = put(kept, "pace", "slow")  # said afresh in this trip
    assert votes_from_state(again) == {"pace": "slow"}


def test_visited_and_unmatched_anchors_are_not_votes(catalog):
    from trip.state import Anchor
    s = put(TripState(), "visited", "0x1:0x1", op="add")
    s = put(s, "anchor", Anchor(text="somewhere", state="missing"), op="add")
    assert votes_from_state(s) == {}
    s = put(s, "anchor", Anchor(text="A", place_id=catalog.places[0].id, state="matched"), op="add")
    assert votes_from_state(s) == {f"place:{catalog.places[0].id}": "love"}


# ---------- seed / prior card ----------

def patterns(catalog):
    pid = catalog.places[0].id
    h = hist("pace", ["slow"] * 3) + hist("soft:crowd=low", ["love"] * 3) + hist(f"place:{pid}", ["love"] * 3)
    h += hist("soft:not_in_ontology=x", ["love"] * 3)
    return detect(h, PCFG, TODAY)


def test_seed_marks_values_as_profile_priors_and_skips_unknown_ones(catalog):
    s = seed(TripState(), patterns(catalog), catalog, PCFG)
    assert s.pace.source == "profile" and s.pace.confidence == "medium" and not s.pace.locked
    assert s.soft["crowd=low"].source == "profile"
    assert not s.anchors  # a stored place is offered, never put in the trip
    assert "soft:not_in_ontology=x" not in s.meta.prior and f"place:{catalog.places[0].id}" in s.meta.prior


def test_prior_card_confirms_in_one_touch(catalog):
    q = prior_q(seed(TripState(), patterns(catalog), catalog, PCFG), catalog)
    assert q.qid == "prior" and q.tier == 2
    assert {c.id for c in q.chips} == {"keep", "fresh", f"place:{catalog.places[0].id}"}
    assert q.multi and q.single_rows == ("Như mọi lần",)


def test_prior_card_is_single_choice_without_places(catalog):
    s = seed(TripState(), hist_patterns(catalog, "pace", ["slow"] * 3), catalog, PCFG)
    q = prior_q(s, catalog)
    assert not q.multi and [c.id for c in q.chips] == ["keep", "fresh"]


def hist_patterns(catalog, key, values):
    return detect(hist(key, values), PCFG, TODAY)


def test_no_prior_card_once_asked_or_replaced(catalog):
    s = seed(TripState(), hist_patterns(catalog, "pace", ["slow"] * 3), catalog, PCFG)
    assert prior_q(with_meta(s, asked=("prior",)), catalog) is None
    assert prior_q(put(s, "pace", "packed"), catalog) is None  # the trip said otherwise: nothing left to confirm


def test_effort_limit_drops_a_stored_push_toward_effort(catalog):
    h = hist("soft:hiking=present", ["love"] * 3) + hist("pace", ["packed"] * 3) + hist("soft:crowd=low", ["love"] * 3)
    s = seed(TripState(), detect(h, PCFG, TODAY), catalog, PCFG)
    assert "hiking=present" in s.soft and s.pace.value == "packed"
    s = settle(put(s, "signal", "elderly", op="add"))
    assert "hiking=present" not in s.soft and not s.pace.known and "crowd=low" in s.soft


def test_effort_limit_keeps_what_the_user_said(catalog):
    s = put(TripState(), "soft", ("hiking=present", "love"), op="add")
    assert "hiking=present" in settle(put(s, "signal", "elderly", op="add")).soft


# ---------- store ----------

def test_store_round_trip_and_replace_by_session(tmp_path):
    st = ProfileStore(tmp_path, PCFG)
    st.record(UID, Summary(sid="a", day=TODAY, votes={"pace": "slow"}))
    st.record(UID, Summary(sid="a", day=TODAY, votes={"pace": "packed"}))
    assert [h.votes for h in st.history(UID)] == [{"pace": "packed"}]
    assert st.forget(UID) and not st.forget(UID) and st.history(UID) == []


def test_store_rejects_ids_that_could_leave_the_directory(tmp_path):
    for bad in ("../x", "a/b", "short", ""):
        with pytest.raises(ValueError):
            ProfileStore(tmp_path, PCFG).history(bad)


def test_unreadable_file_is_an_empty_history(tmp_path):
    (tmp_path / f"{UID}.json").write_text("{not json")
    assert ProfileStore(tmp_path, PCFG).history(UID) == []


# ---------- engine ----------

@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "profiles", PCFG)


@pytest.fixture
def make(catalog, cfg, store):
    def build(profiles=store, agent=None):
        return Engine(catalog, cfg, SessionStore(None), agent or FakeAgent(error=AgentError("down")),
                      today=lambda: TODAY, profiles=profiles)
    return build


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def to_dates(e, sid):
    run(e, sid, kind="answer", qid="frame", chips=("days:3", "who:solo", "mobility:car"))
    return run(e, sid, kind="answer", qid="dates", chips=("undecided",))


def learn(store, catalog):
    for i in range(3):
        store.record(UID, Summary(sid=f"old{i}", day=TODAY - timedelta(days=10 - i),
                                  votes={"pace": "slow", "soft:crowd=low": "love", f"place:{catalog.places[0].id}": "love"}))


def test_stored_patterns_seed_a_session_and_the_card_comes_after_the_frame(make, store, catalog):
    learn(store, catalog)
    e = make()
    v = e.create("returning", "nothing", UID, True)
    assert v["card"]["qid"] == "frame"  # the blocking questions still come first
    sid = v["id"]
    ev = to_dates(e, sid)
    assert ev[-1][1]["qid"] == "prior"
    assert e.store.get(sid).state.pace.source == "profile"


def test_keep_confirms_and_fresh_clears_without_asking_again(make, store, catalog):
    learn(store, catalog)
    e = make()
    sid = e.create("returning", "nothing", UID, True)["id"]
    to_dates(e, sid)
    run(e, sid, kind="answer", qid="prior", chips=("keep",))
    st = e.store.get(sid).state
    assert st.pace.locked and st.pace.value == "slow" and "crowd=low" in st.soft
    e2 = make()
    sid2 = e2.create("returning", "nothing", UID, True)["id"]
    to_dates(e2, sid2)
    run(e2, sid2, kind="answer", qid="prior", chips=("fresh",))
    st2 = e2.store.get(sid2).state
    assert not st2.pace.known and "crowd=low" not in st2.soft and "prior" in st2.meta.asked


def test_a_place_pattern_is_added_only_when_chosen(make, store, catalog):
    learn(store, catalog)
    e = make()
    sid = e.create("returning", "nothing", UID, True)["id"]
    to_dates(e, sid)
    run(e, sid, kind="answer", qid="prior", chips=("fresh", f"place:{catalog.places[0].id}"))
    (a,) = e.store.get(sid).state.anchors
    assert a.place_id == catalog.places[0].id and a.priority == "want"


def test_editing_the_panel_refreshes_a_pending_prior_card(make, store, catalog):
    learn(store, catalog)
    e = make()
    sid = e.create("returning", "nothing", UID, True)["id"]
    to_dates(e, sid)
    ev = run(e, sid, kind="edit", target="pace", value="packed")
    card = [d for n, d in ev if n == "card"][-1]
    assert card["qid"] == "prior" and "thong thả" not in card["text"]


def test_no_profile_without_a_store_or_user_id(make, store, catalog):
    learn(store, catalog)
    assert make(profiles=None).create("returning", "nothing", UID, True)["card"]["qid"] == "frame"
    e = make()
    sid = e.create("returning", "nothing")["id"]
    assert e.store.get(sid).state.meta.prior == () and not e.store.get(sid).state.pace.known


def test_session_is_remembered_only_with_consent_and_once(make, store):
    for remember, expect in ((False, 0), (True, 1)):
        e = make()
        sid = e.create("first", "nothing", UID, remember)["id"]
        to_dates(e, sid)
        run(e, sid, kind="edit", target="pace", value="packed")
        run(e, sid, kind="show")
        run(e, sid, kind="show")
        assert len(store.history(UID)) == expect
    assert store.history(UID)[0].votes == {"pace": "packed"}


def test_forget_deletes_the_history(make, store):
    store.record(UID, Summary(sid="a", day=TODAY, votes={"pace": "slow"}))
    assert make().forget(UID) and store.history(UID) == []
    assert make(profiles=None).forget(UID) is False


# ---------- idle stop ----------

def test_adaptive_questions_that_add_nothing_end_the_questions(make):
    asking = {"say": "Ghi rồi. Còn gì nữa không?", "updates": [],
              "next": {"kind": "ask", "qid": "", "custom_text": "Bạn nghĩ sao?", "custom_chips": ["Ý một", "Ý hai"],
                       "reason": ""}}
    e = make(agent=FakeAgent(asking))
    sid = e.create("first", "nothing")["id"]
    to_dates(e, sid)
    run(e, sid, kind="text", text="ừm")
    assert e.load(sid)["card"]["custom"] and e.store.get(sid).state.meta.idle_streak == 1
    ev = run(e, sid, kind="text", text="ừm nữa")
    assert e.load(sid)["card"]["qid"] == "ready" and "?" not in next(d for n, d in ev if n == "say")["replace"]


def test_skipping_still_offers_to_show_first(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    to_dates(e, sid)
    for _ in range(2):
        run(e, sid, kind="answer", qid=e.load(sid)["card"]["qid"], chips=("skip",))
    assert e.load(sid)["card"]["qid"] == "show_first"


def test_useful_questions_run_until_the_turn_budget(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    to_dates(e, sid)
    answered = 0
    while (c := e.load(sid)["card"])["qid"] != "ready" and answered < 30:
        chip = next(x["id"] for x in c["chips"] if x["id"] not in ("skip", "unsure"))
        run(e, sid, kind="answer", qid=c["qid"], chips=(chip,))
        answered += 1
    st = e.store.get(sid).state
    assert st.meta.idle_streak == 0 and answered == st.meta.adaptive_turns <= 5
