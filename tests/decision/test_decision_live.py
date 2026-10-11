import time

import pytest
from test_decision_engine import data, trip

from decision.agent import run_agent
from decision.engine import Engine
from decision.session import Store
from decision.settings import default


@pytest.mark.live
def test_one_real_turn_drops_the_named_place():
    cfg = default()
    e = Engine(data(), cfg, Store(None), lambda f, on_say: run_agent(f, on_say, cfg))
    sid = e.create(trip())["id"]
    events = []
    t0 = time.perf_counter()
    e.turn(sid, "Quán Cà Phê Số 1 xa quá, bỏ giúp mình", lambda ev, d: events.append((ev, d)))
    s = e.store.get(sid)
    print(f"turn {time.perf_counter() - t0:.1f}s", ascii(events[0]), ascii(s.log[-1]))
    assert not any("agent_fallback" in x for x in s.log[-1]["action"]["log"])
    assert [(d.place_id, d.reason) for d in s.state.dropped] == [("C1", "far")]
