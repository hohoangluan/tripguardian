"""Wish scoring stays fast on the real snapshot (spec §12.1 G). Baseline 2026-10-15, 3,208 places, 30 eval trips:
first run median 59 ms / p95 100 ms; memo hit median 17 ms."""

import statistics
import time

import pytest

from corpus.ontology import load
from decision import eval_search_input, eval_trips, frame
from decision.pipeline import Data, run
from decision.session import Session, State
from decision.settings import default
from decision.wishes import build
from corpus.serving import dishes

DISHES = ("lẩu gà lá é", "bánh căn", "bánh tráng nướng")  # real dish hits, as Trip's find_dishes builds them

CFG = default()
pytestmark = pytest.mark.corpus


@pytest.fixture(scope="module")
def region():
    snap = pytest.importorskip("corpus.snapshot")
    try:
        return snap.shared().region().warm()
    except FileNotFoundError:
        pytest.skip("no snapshot")


_hits: dict = {}


def dish_ids(region, name):
    if name not in _hits:
        _hits[name] = [h["id"] for h in dishes.search(region.records(), name)]
    return _hits[name]


def wished(si_, region):
    ids, groups = region.ids, region.column("category_group")
    cafes = [p for p, g in zip(ids, groups) if g == "cafe"]
    ref = max(cafes, key=lambda p: len(region.sigs[p]))
    data = si_.model_dump(mode="json")
    data["wishes"] = {"dishes": [{"dish": d, "quote": d, "place_ids": dish_ids(region, d)} for d in DISHES],
                      "kinds": [{"kind": "cà phê", "quote": "cà phê", "place_ids": cafes[:40]},
                                {"kind": "bar", "quote": "bar", "place_ids": [p for p, g in zip(ids, groups) if g == "bar"]}],
                      "like": [{"place_id": ref, "but": [], "quote": "giống"}]}
    data["liked_groups"] = ["chill", "nature"]
    data["context"]["purpose"] = "relax"
    return type(si_).model_validate(data)


def inputs(region):
    version, trips = eval_trips()
    ov = load().version
    return [wished(eval_search_input(t, version).model_copy(update={"ontology_version": ov}), region) for t in trips]


def ms(fn) -> float:
    def once():
        t = time.perf_counter()
        fn()
        return time.perf_counter() - t
    return statistics.median(once() for _ in range(3)) * 1000


def test_first_run_p95_within_budget(region):  # G1
    data = Data(region=region)
    times = sorted(ms(lambda: run(Session(id="0" * 12, search_input=s, state=State()), data, CFG, {}))
                   for s in inputs(region))
    p95 = times[int(0.95 * len(times)) - 1]
    assert p95 <= 120, f"p95 {p95:.0f} ms"


def test_memo_hit_median_within_budget(region):  # G2
    data = Data(region=region)
    times = []
    for s in inputs(region):
        session, memo = Session(id="0" * 12, search_input=s, state=State()), {}
        run(session, data, CFG, memo)
        times.append(ms(lambda: run(session, data, CFG, memo)))
    assert statistics.median(times) <= 20, f"median {statistics.median(times):.0f} ms"


def test_like_build_is_cheap(region):  # G3
    s = inputs(region)[0]
    t = ms(lambda: build(s, region.light, CFG, region.sigs, frame.firm_ids(region)))
    assert t <= 10, f"{t:.1f} ms"


def test_memo_hit_rebuilds_neither_wishes_nor_scores(region, monkeypatch):  # G4
    calls = {"score": 0, "wishes": 0}
    real_score, real_build = frame.score_table, frame.build_wishes

    def count(name, fn):
        def wrapped(*a, **k):
            calls[name] += 1
            return fn(*a, **k)
        return wrapped

    monkeypatch.setattr(frame, "score_table", count("score", real_score))
    monkeypatch.setattr(frame, "build_wishes", count("wishes", real_build))
    session, memo, data = Session(id="0" * 12, search_input=inputs(region)[0], state=State()), {}, Data(region=region)
    run(session, data, CFG, memo)
    calls.update(score=0, wishes=0)
    run(session, data, CFG, memo)
    assert calls == {"score": 0, "wishes": 0}
