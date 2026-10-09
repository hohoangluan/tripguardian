import asyncio
import json
import time

import pytest

from corpus.crawl.gmaps import gate as gate_mod
from corpus.crawl.gmaps.gate import Gate, GateThrottle


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.setattr(gate_mod, "CACHE_S", 0)  # every read sees the file
    monkeypatch.setattr(gate_mod, "BASE_COOL_S", 180)  # conftest zeroes them for the other tests
    monkeypatch.setattr(gate_mod, "MAX_COOL_S", 1200)
    return Gate(tmp_path / "block.json")


def test_no_file_means_no_wait_and_no_penalty(gate):
    assert gate.wait_s() == 0 and gate.penalty() == 0


def test_first_block_rests_every_tab_and_takes_one_tab_off(gate):
    gate.report_block()
    assert 170 < gate.wait_s() <= gate_mod.BASE_COOL_S and gate.penalty() == 1


def test_many_tabs_reporting_the_same_block_count_once(gate):
    for _ in range(50):
        gate.report_block()
    assert gate.penalty() == 1


def test_next_block_doubles_the_cooldown_and_is_capped(gate, tmp_path):
    gate.report_block()
    state = json.loads((tmp_path / "block.json").read_text())
    state["stepped_at"] -= 120  # a second, separate block
    (tmp_path / "block.json").write_text(json.dumps(state))
    gate.report_block()
    assert gate.penalty() == 2 and 350 < gate.wait_s() <= 2 * gate_mod.BASE_COOL_S
    state = {"until": 0, "penalty": gate_mod.MAX_PENALTY, "last_block": time.time(), "stepped_at": 0}
    (tmp_path / "block.json").write_text(json.dumps(state))
    gate.report_block()
    assert gate.wait_s() <= gate_mod.MAX_COOL_S


def test_penalty_fades_one_step_per_clean_decay(gate, tmp_path):
    state = {"until": 0, "penalty": 3, "last_block": time.time() - 2.5 * gate_mod.DECAY_S, "stepped_at": 0}
    (tmp_path / "block.json").write_text(json.dumps(state))
    assert gate.penalty() == 1


def test_throttle_opens_fewer_tabs_while_penalised_and_waits_out_the_cooldown(gate, tmp_path):
    state = {"until": 0, "penalty": 2, "last_block": time.time(), "stepped_at": time.time()}
    (tmp_path / "block.json").write_text(json.dumps(state))
    t = GateThrottle(tmp_path / "throttle.json", start=4, hi=4, gate=gate)
    t.fixed, t.limit = True, 4

    async def go():
        await t.__aenter__()
        await t.__aenter__()  # 4 tabs - penalty 2 = 2 open
        third = asyncio.create_task(t.__aenter__())
        await asyncio.sleep(0.2)
        assert not third.done()  # no third tab while penalised
        await t.__aexit__(None, None, None)
        await asyncio.wait_for(third, 6)  # a slot freed: it opens

    asyncio.run(go())
    assert t._active == 2


def test_a_captcha_waiting_for_a_person_keeps_every_tab_resting(gate):
    gate.hold()
    assert 50 < gate.wait_s() <= gate_mod.HOLD_S


def test_a_solved_captcha_ends_the_rest_but_keeps_the_penalty(gate):
    gate.report_block()
    before = gate.solved_at()
    gate.solved()
    assert gate.wait_s() == 0 and gate.penalty() == 1 and gate.solved_at() > before
