"""Clef reply and fact checks on labelled cases (tests/trip/clef_cases.yaml), against the real Cloudflare model; measured and
printed (python -m pytest --collect-in-virtualenv -m live tests/trip/test_clef_live.py -s)."""

from pathlib import Path

import pytest
import yaml

from trip.infrastructure import clef
from trip.infrastructure.settings import Settings

pytestmark = pytest.mark.live
CASES = yaml.safe_load((Path(__file__).parent / "clef_cases.yaml").read_text(encoding="utf-8"))


def test_reply_and_support_checks():
    j, bad = clef.Judge(Settings()), []
    for c in CASES["reply"]:
        if (got := j.bad_reply(c["say"], c["user"])) != c["expect"]:
            bad.append(("reply", c["say"], c["expect"], got))
    for c in CASES["support"]:
        if (got := j.unsupported(c["quote"], c["claim"])) != c["expect"]:
            bad.append(("support", c["quote"], c["claim"], c["expect"], got))
    print(f"\nreply + support: {len(CASES['reply']) + len(CASES['support'])} cases, wrong {len(bad)}")
    for b in bad:
        print("  ", b)
    shown_wrongly_replaced = [b for b in bad if b[0] == "reply" and b[2] is None]
    refused_true_facts = [b for b in bad if b[0] == "support" and b[3] is False]
    assert not shown_wrongly_replaced and not refused_true_facts
