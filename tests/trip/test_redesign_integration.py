"""Boundary regressions for the redesigned planning inputs."""

from trip import TripState, compile_search_input, readiness_missing
from trip.domain.state import Evidence, Update, apply


def said(value):
    return {"value": value, "source": "user", "confidence": "high", "status": "confirmed",
            "evidence": [{"turn": 1, "quote": "q"}]}


def test_listed_care_needs_an_actual_limit():
    state = TripState.model_validate({"care": said("listed")})
    assert "care" in dict(readiness_missing(state))


def test_a_direct_signal_is_kept_after_removing_its_inferred_companion():
    def put(state, field, value, quote, source="user", op="set", turn=1):
        return apply(state, Update(field=field, value=value, source=source, confidence="high", op=op,
                                   evidence=Evidence(turn=turn, quote=quote)))

    state = put(TripState(), "companions", ["parents"], "bố mẹ")
    state = put(state, "signal", "elderly", "bố mẹ", source="inferred")
    state = put(state, "signal", "elderly", "bà lớn tuổi cần nghỉ", turn=2)
    state = put(state, "companions", ["parents"], "bỏ bố mẹ", op="remove", turn=3)
    assert [(s.kind, s.quote, s.from_companion) for s in state.signals] == [
        ("elderly", "bà lớn tuổi cần nghỉ", None)]


def test_an_unlimited_budget_does_not_send_a_stale_cap_downstream():
    state = TripState.model_validate({"budget_vnd": said(800_000), "budget_scope": said("per_person_day"),
                                      "budget_unlimited": said(True)})
    context = compile_search_input(state).context
    assert context.budget_unlimited is True and context.budget_vnd is None and context.budget_intent is None


def test_engine_records_frame_facts_without_leaking_the_field_name(catalog, cfg, tmp_path):
    from datetime import date
    from trip.api.engine import Engine, TurnInput
    from trip.infrastructure.sessions import SessionStore
    from trip_fixtures import ScriptedChat, fact, reply, say

    text = "lái tối đa 2 tiếng mỗi ngày"
    chat = ScriptedChat(reply(fact("drive_day_min", "120", text)), say(""))
    engine = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = engine.create("first", "nothing")["id"]
    events = []
    engine.turn(sid, TurnInput(kind="text", text=text), lambda kind, data: events.append((kind, data)))
    assert engine.store.get(sid).state.frame.drive_day_min.value == 120
    assert all("drive_day_min" not in str(data) for kind, data in events if kind == "say")
