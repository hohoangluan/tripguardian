"""The agent's web tools inside one turn: only what web_search returned may be read, a failure is a visible step and
the turn goes on, and the ask tool is only offered where a card can be answered."""

from datetime import date

import pytest

from trip.agent.tools import TurnTools
from trip.domain.state import TripState
from trip.infrastructure.web import WebHit, WebPage

TEXT = "tui muốn quán phong cách wabi sabi"


class FakeWeb:
    def __init__(self, fail=False):
        self.fail, self.read_urls = fail, []

    def search(self, query, k=5):
        if self.fail:
            raise TimeoutError("searx down")
        return [WebHit(url="https://a.vn/x", title="Wabi sabi là gì", domain="a.vn", snippet="..."),
                WebHit(url="https://b.vn/y", title="Phong cách", domain="b.vn", snippet="...")]

    def read(self, url, max_chars=6000):
        self.read_urls.append(url)
        return WebPage(url=url, title="Wabi sabi", domain="a.vn", text="vẻ đẹp không hoàn hảo, gỗ thô")


def tools(catalog, web=None, cards=True, trace=None):
    return TurnTools(TripState(), TEXT, 1, catalog, date(2026, 10, 2), web=web, cards=cards,
                     on_trace=(trace.append if trace is not None else None))


def names(t):
    return [s["function"]["name"] for s in t.specs()]


def test_web_tools_are_offered_only_with_a_web_and_ask_only_where_a_card_can_be_answered(catalog):
    assert "web_search" not in names(tools(catalog)) and "ask" in names(tools(catalog))
    assert {"web_search", "web_read"} <= set(names(tools(catalog, FakeWeb())))
    t = tools(catalog, cards=False)
    assert "ask" not in names(t) and "error" in t.run("ask", {"kind": "look", "about": "wabi sabi", "cues": ["gỗ thô"]})


def test_search_shows_a_step_and_only_found_pages_may_be_read(catalog):
    trace, web = [], FakeWeb()
    t = tools(catalog, web, trace=trace)
    out = t.run("web_search", {"query": "wabi sabi là gì"})
    assert len(out["results"]) == 2 and "data, not instructions" in out["note"]
    assert [s["status"] for s in (trace[0]["steps"][0], trace[-1]["steps"][0])] == ["run", "ok"]
    assert "2 nguồn" in trace[-1]["steps"][0]["label"]
    assert "error" in t.run("web_read", {"url": "https://evil.test/z"}) and not web.read_urls
    t.run("web_read", {"url": "https://a.vn/x"})
    t.run("web_read", {"url": "https://a.vn/x"})
    assert [s["url"] for s in t.sources] == ["https://a.vn/x"]


def test_a_failed_search_is_a_failed_step_not_a_failed_turn(catalog):
    trace = []
    t = tools(catalog, FakeWeb(fail=True), trace=trace)
    out = t.run("web_search", {"query": "wabi sabi"})
    assert "error" in out and trace[-1]["steps"][0]["status"] == "fail"


@pytest.mark.parametrize("args,ok", [
    ({"kind": "look", "about": "wabi sabi", "cues": ["Gỗ Thô", "gỗ thô", "đồ gốm mộc"], "where": "cafe"}, True),
    ({"kind": "look", "about": "wabi sabi", "cues": ["gỗ thô"], "where": "spa"}, False),
    ({"kind": "look", "about": "kiểu Hàn", "cues": ["gỗ thô"]}, False),
])
def test_ask_look_checks_its_arguments(catalog, args, ok):
    t = tools(catalog)
    out = t.run("ask", args)
    assert ("error" not in out) == ok
    if ok:
        assert t.asked["cues"] == ["gỗ thô", "đồ gốm mộc"] and t.asked["where"] == "cafe"
        assert "error" in t.run("ask", args)  # one card per turn
