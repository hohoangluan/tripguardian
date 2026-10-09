"""The test conversations of config/eval_trips.yaml: offline with the keyword rules only, live with the real Agent."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from trip_fixtures import ScriptedChat

from trip import TurnInput, compile_search_input
from trip.agent import AgentError
from trip.api.engine import Engine
from trip.domain.budget import per_person_day
from trip.infrastructure.sessions import SessionStore

ROOT = Path(__file__).resolve().parents[2]
CONVERSATIONS = yaml.safe_load((ROOT / "config" / "eval_trips.yaml").read_text(encoding="utf-8"))["conversations"]


def got(state, field):
    if field == "budget_ppd":
        return per_person_day(state)
    if field == "soft":
        return [f"{k}:{f.value}" for k, f in state.soft.items()]
    v = getattr(state, field).value
    return sorted(v) if isinstance(v, frozenset) else list(v) if isinstance(v, tuple) else v


def check(state, expect):
    for field, want in expect.items():
        have = got(state, field)
        if field == "soft":
            assert set(want) <= set(have), (field, have)
        else:
            assert have == want, (field, have)


def talk(engine, turns):
    sid = engine.create("first", "nothing")["id"]
    for text in turns:
        engine.turn(sid, TurnInput(kind="text", text=text), lambda e, d: None)
    return engine.store.get(sid).state


@pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c["id"] for c in CONVERSATIONS])
def test_the_keyword_rules_alone_read_the_test_conversations(conv, catalog, cfg, tmp_path):
    engine = Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat(error=AgentError("down")),
                    today=lambda: date(2026, 10, 9))
    state = talk(engine, conv["turns"])
    check(state, conv["expect"])
    compile_search_input(state)  # nothing open blocks the hand-off


@pytest.mark.live
@pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c["id"] for c in CONVERSATIONS])
def test_the_agent_reads_the_test_conversations(conv):
    from trip import create_engine
    state = talk(create_engine(ROOT / "data"), conv["turns"])
    check(state, {**conv["expect"], **conv.get("expect_live", {})})
