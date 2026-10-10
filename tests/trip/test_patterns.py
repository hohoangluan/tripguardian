"""Long-term pattern learning (docs/P2_TRIP_UNDERSTANDING.md §17)."""

from datetime import date, timedelta

import pytest
from trip_fixtures import ScriptedChat

from trip.agent import AgentError
from trip.api.engine import Engine, TurnInput
from trip.domain.patterns import Summary, detect, seed, votes_from_state
from trip.infrastructure.profile import ProfileStore
from trip.infrastructure.sessions import SessionStore
from trip.infrastructure.settings import PatternSettings, Settings
from trip.domain.state import Evidence, TripState, Update, apply, settle

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
    from trip.domain.state import Anchor
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
    def build(profiles=store, chat=None):
        return Engine(catalog, cfg, SessionStore(None), chat or ScriptedChat(error=AgentError("down")),
                      today=lambda: TODAY, profiles=profiles)
    return build


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def learn(store, catalog):
    for i in range(3):
        store.record(UID, Summary(sid=f"old{i}", day=TODAY - timedelta(days=10 - i),
                                  votes={"pace": "slow", "soft:crowd=low": "love", f"place:{catalog.places[0].id}": "love"}))


def test_stored_patterns_seed_a_session_as_profile_priors_without_a_card(make, store, catalog):
    learn(store, catalog)
    e = make()
    v = e.create("returning", "nothing", UID, True)
    assert v["card"]["qid"] == "frame"  # the user is never asked to confirm a stored taste: the agent just sees its source
    assert e.store.get(v["id"]).state.pace.source == "profile"


def test_no_profile_without_a_store_or_user_id(make, store, catalog):
    learn(store, catalog)
    assert make(profiles=None).create("returning", "nothing", UID, True)["card"]["qid"] == "frame"
    e = make(profiles=None)
    assert not e.store.get(e.create("returning", "nothing", UID, True)["id"]).state.pace.known
    e = make()
    sid = e.create("returning", "nothing")["id"]
    assert e.store.get(sid).state.meta.prior == () and not e.store.get(sid).state.pace.known


def test_session_is_remembered_only_with_consent_and_once(make, store):
    for remember, expect in ((False, 0), (True, 1)):
        e = make()
        sid = e.create("first", "nothing", UID, remember)["id"]
        run(e, sid, kind="edit", target="pace", value="packed")
        for field, value in (("days", "2"), ("companions", "solo"), ("mobility", "car"), ("month", "12")):
            run(e, sid, kind="edit", target=field, value=value)
        run(e, sid, kind="show")
        run(e, sid, kind="show")
        assert len(store.history(UID)) == expect
    assert store.history(UID)[0].votes == {"pace": "packed", "mobility": "car"}  # what the user chose by hand is voted


def test_forget_deletes_the_history(make, store):
    store.record(UID, Summary(sid="a", day=TODAY, votes={"pace": "slow"}))
    assert make().forget(UID) and store.history(UID) == []
    assert make(profiles=None).forget(UID) is False




# ---------- account profile as a prior ----------

def test_profile_fields_seed_as_priors_that_the_trip_overrides():
    from trip.domain.patterns import seed_profile
    s = seed_profile(TripState(), {"usual_mobility": "motorbike", "usual_companions": "partner", "home_city": "Huế"})
    assert (s.mobility.value, s.mobility.source) == ("motorbike", "profile")
    assert s.companions.value == frozenset({"partner"}) and s.companions.source == "profile"
    assert s.origin.value is None  # a typed city has no point for the logistics search
    told = apply(s, Update(field="mobility", value="car", source="user", confidence="high",
                           evidence=Evidence(turn=1, quote="đi ô tô")))
    assert (told.mobility.value, told.mobility.source) == ("car", "user")


def test_profile_values_trip_does_not_know_are_ignored():
    from trip.domain.patterns import seed_profile
    s = seed_profile(TripState(), {"usual_mobility": "rocket", "usual_companions": None})
    assert s.mobility.value is None and s.companions.value is None


# ---------- the logistics answers are learned too, so later trips ask less ----------

import json

from trip.domain.questions import quiz_queue
from trip.domain.state import Base

HCM = Base(text="TP Hồ Chí Minh", lat=10.7769, lng=106.7009, province="TP Hồ Chí Minh")


def said(state, field, value):
    return settle(apply(state, Update(field=field, value=value, source="user", confidence="high",
                                      evidence=Evidence(turn=1, tool="chip:test"))))


def test_how_they_arrive_where_from_budget_and_hours_are_voted_when_chosen():
    st = TripState()
    for field, value in (("arrival_mode", "bus"), ("mobility", "motorbike"), ("origin", HCM), ("budget_vnd", 700_000),
                         ("checkin_at", "14:00"), ("checkout_at", "11:00")):
        st = said(st, field, value)
    votes = votes_from_state(st)
    assert {k: votes[k] for k in ("arrival_mode", "mobility", "budget_vnd", "checkin_at", "checkout_at")} == \
        {"arrival_mode": "bus", "mobility": "motorbike", "budget_vnd": "700000", "checkin_at": "14:00", "checkout_at": "11:00"}
    assert json.loads(votes["origin"])["province"] == "TP Hồ Chí Minh"


def test_a_value_seeded_from_a_pattern_is_not_voted_again():
    st = said(TripState(), "checkin_at", "14:00")
    st = settle(apply(st, Update(field="arrival_mode", value="bus", source="profile", confidence="medium",
                                 evidence=Evidence(turn=0, tool="profile:arrival_mode"))))
    assert "arrival_mode" not in votes_from_state(st) and "checkin_at" in votes_from_state(st)


def test_learned_logistics_are_seeded_as_priors_and_the_quiz_stops_asking_them(catalog):
    from trip.domain.patterns import Pattern
    cfg = PatternSettings(enabled=True, min_sessions=2)
    found = [Pattern(key="arrival_mode", value="bus", sessions=3, confidence="medium", last=TODAY),
             Pattern(key="origin", value=json.dumps({"text": HCM.text, "lat": HCM.lat, "lng": HCM.lng,
                                                     "province": HCM.province}), sessions=3, confidence="medium", last=TODAY),
             Pattern(key="budget_vnd", value="700000", sessions=3, confidence="medium", last=TODAY),
             Pattern(key="checkin_at", value="14:00", sessions=3, confidence="medium", last=TODAY),
             Pattern(key="checkout_at", value="11:00", sessions=3, confidence="medium", last=TODAY)]
    st = seed(TripState(), found, catalog, cfg)
    assert (st.arrival_mode.value, st.origin.value.province, st.budget_vnd.value, st.checkin_at.value) == \
        ("bus", "TP Hồ Chí Minh", 700_000, "14:00")
    assert st.arrival_mode.source == "profile" and st.origin.source == "profile"
    qids = [q.qid for q in quiz_queue(st, catalog, Settings(n_min=1, top_k=4, enough_factor=1.0))]
    assert not {"arrival", "origin", "budget", "stay_times"} & set(qids)


def test_this_trips_own_answer_replaces_a_learned_prior(catalog):
    from trip.domain.patterns import Pattern
    st = seed(TripState(), [Pattern(key="arrival_mode", value="bus", sessions=3, confidence="medium", last=TODAY)],
              catalog, PatternSettings(enabled=True, min_sessions=2))
    st = said(st, "arrival_mode", "plane")
    assert st.arrival_mode.value == "plane" and st.arrival_mode.source == "user"
