"""Real Gemma calls: python -m pytest -m live tests/trip/test_live.py -s (needs UIT network + AGENT_* in .env)."""

import asyncio
import time
from datetime import date

import pytest

from trip.agent import prompt_fields, run_agent
from trip.prepass import prepass
from trip.settings import load
from trip.state import TripState

pytestmark = pytest.mark.live
MESSAGES = ["Tháng 12 đi Đà Lạt 3 ngày với bố mẹ, mẹ đau gối, muốn chill",
            "2 vợ chồng đi xe máy, thích săn mây với cà phê view đồi",
            "đi 4 người bạn, không quá 500k/người, thích chỗ đông vui có nhạc sống",
            "lần trước đi Langbiang rồi, lần này muốn khác",
            "chưa biết đi đâu, gợi ý giúp"]


@pytest.mark.parametrize("text", MESSAGES)
def test_gemma_returns_a_valid_plan(text):
    cfg, today = load(), date.today()
    fields = prompt_fields(TripState(), text, prepass(text, today), None, [], cfg, None, today)
    first, t0 = [], time.monotonic()
    plan = asyncio.run(run_agent(fields, lambda s: first or first.append(time.monotonic() - t0), cfg))
    shown = f"{first[0]:.1f}s" if first else "none"
    print(f"\n{text}\n  first say {shown} total {time.monotonic() - t0:.1f}s\n  {plan}")
    assert plan.say
