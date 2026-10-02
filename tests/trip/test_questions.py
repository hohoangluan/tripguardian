from datetime import date

from trip.policy import askable, next_question
from trip.questions import READY, bank, rank_questions, required
from trip.state import Anchor, Evidence, TripState, Update, apply, with_meta

EV = Evidence(turn=1, quote="x")


def up(s, field, value=None, op="set"):
    return apply(s, Update(field=field, op=op, value=value, source="user", confidence="high", evidence=EV))


def framed(**meta):
    s = up(up(up(TripState(), "days", 3), "companions", "solo", "add"), "mobility", "motorbike")
    s = up(s, "start_date", date(2026, 12, 14))  # a Monday
    return with_meta(s, **({"asked": ("frame",)} | meta))


def test_frame_comes_first(catalog, cfg):
    q = required(TripState(), catalog, cfg)
    assert q.qid == "frame" and {c.row for c in q.chips} == {"Số ngày", "Đi với ai", "Đi lại bằng"}


def test_missing_frame_fields_are_asked_one_by_one(catalog, cfg):
    s = with_meta(up(TripState(), "days", 3), asked=("frame",))
    assert required(s, catalog, cfg).qid == "companions"


def test_effort_signal_beats_everything(catalog, cfg):
    s = up(TripState(), "signal", "knee", "add")
    q = required(s, catalog, cfg)
    assert q.qid == "c_effort" and q.exit_drafts


def test_thin_coverage_asks_unknown_policy_with_real_counts(catalog, cfg):
    s = up(framed(), "hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    q = required(s, catalog, cfg)
    assert q.qid == "policy:steep_or_stairs" and "1 nơi" in q.text and "16 nơi" in q.text


def test_ambiguous_anchor_is_asked(catalog, cfg):
    s = up(framed(), "anchor", Anchor(text="Quán Yên", state="choose", candidates=("0x1:0x1", "0x2:0x1")), "add")
    q = required(s, catalog, cfg)
    assert q.qid == "anchor:0" and [c.drafts[0].value for c in q.chips][:2] == [(0, "0x1:0x1"), (0, "0x2:0x1")]


def test_anchor_closed_on_a_trip_day_is_a_conflict(catalog, cfg):
    s = up(framed(), "anchor", Anchor(text="Vườn", place_id="0x11:0x1", state="matched"), "add")
    q = required(s, catalog, cfg)
    assert q.qid == "closed:0" and "14/12" in q.text


def test_rank_prefers_questions_that_change_the_shortlist(catalog, cfg):
    scores = {q.qid: sc for q, sc in rank_questions(framed(), catalog, cfg)}
    assert scores["purpose"] > 0 and scores["pace"] == 0


def test_policy_ready_when_budget_is_spent(catalog, cfg):
    assert next_question(framed(adaptive_turns=5), catalog, cfg) is READY


def test_policy_ready_when_nothing_changes_results(catalog, cfg):
    s = framed(asked=("frame", "purpose", "vibe", "crowd", "pace", "max_leg", "budget", "times"))
    assert next_question(s, catalog, cfg) is READY


def test_unsure_twice_offers_show_first(catalog, cfg):
    assert next_question(framed(unsure_streak=2), catalog, cfg).qid == "show_first"


def test_clarify_uses_pending_keys(catalog, cfg):
    s = up(framed(), "pending", {"phrase": "chill", "keys": ["noise=quiet", "crowd=low"]}, "add")
    q = next_question(s, catalog, cfg)
    assert q.qid == "clarify:chill" and [c.label for c in q.chips] == ["Yên tĩnh", "Ít người"]


def test_first_timer_without_wishes_is_asked_purpose(catalog, cfg):
    assert next_question(framed(experience="first"), catalog, cfg).qid == "purpose"


def test_askable_contains_bank_and_ready(catalog, cfg):
    qs = askable(framed(), catalog, cfg)
    assert "purpose" in qs and "ready" in qs and {q.qid for q in bank(framed(), catalog, cfg)} <= set(qs)
