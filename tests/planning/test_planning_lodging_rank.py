"""Lodging by taste (docs/PLANNING.md ⓐ): served stays once there are enough, taste before location, unknown never
penalised, evidence against a hard filter drops, a late live price never reorders what is shown."""

import pytest
from plan_fixtures import CENTRE, CFG, FakeLive, decision, fake_matrix, no_geocode, rec, sample_trip

from planning.engine import Engine
from planning.lodging import booked, candidates, rank, refresh_prices, with_booked_base
from planning.places import build_places, resolve_point
from planning.session import Store

QUIET = {"feature": "noise", "value": "quiet", "context": None, "weight": 1.0, "source": "user"}
LABELS = {"feature": {"noise": "Độ ồn", "kids": "Hợp trẻ em", "steep_or_stairs": "Dốc, bậc thang"},
          "value": {"quiet": "yên tĩnh"}}


def stay(pid, i, features=None, voices=20, price=None):
    r = rec(pid, CENTRE[0] + i * 0.001, CENTRE[1], group="stay", features=features, name=f"Stay {pid}")
    r["provenance"] = {"voices": voices, "as_of": "2026-10-01", "rating_trend": {"recent_mean": 4.6}}
    r["operation"]["price_per_person"] = {"value": {"min_vnd": price}} if price else None
    return r


def trip(soft=(QUIET,), **kw):
    d = decision(["a"], **kw)
    d["trip_context"]["soft_weights"] = list(soft)
    return d


def places():
    r = rec("a", *CENTRE)
    (p,), _ = build_places(decision(["a"]), {"a": r}, CFG)
    return {"a": p}


def many_stays(n, **kw):
    return [stay(f"s{i}", i % 10, **kw) for i in range(n)]


def test_enough_served_stays_never_crawl():
    cfg = CFG.__class__(**{**CFG.__dict__, "stay_min": 3})
    out = candidates(places(), trip(), cfg, lambda *a: pytest.fail("no crawl"), None, many_stays(3))
    assert {c["source"] for c in out} == {"corpus"} and len(out) == 3


def test_too_few_served_stays_crawl_live_as_before():
    cfg = CFG.__class__(**{**CFG.__dict__, "stay_min": 4})
    card = {"id": "h1", "name": "Live 1", "lat": CENTRE[0], "lng": CENTRE[1], "rating": 4.4, "reviews": 30,
            "price_vnd": 500000, "amenities": [], "source": "gmaps", "fetched_at": "2026-10-08T00:00:00+00:00"}
    out = candidates(places(), trip(), cfg, lambda *a: [card], None, many_stays(3))
    assert [(c["id"], c["source"], c["price_source"]) for c in out] == [("h1", "live", "gmaps")]
    (r,) = rank(out, trip(), {"h1": 5}, cfg)
    assert r["fit"] == []  # no observed reviews: nothing to compare taste on


def test_a_lodging_that_fits_the_taste_ranks_above_a_nearer_one_that_does_not():
    fits = stay("quiet", 5, features={"noise": "quiet"})
    near = stay("near", 0)
    cands = candidates(places(), trip(), CFG.__class__(**{**CFG.__dict__, "stay_min": 2}), None, None, [fits, near])
    out = rank(cands, trip(), {"quiet": 25, "near": 2}, CFG, LABELS)
    assert [c["id"] for c in out] == ["quiet", "near"]
    assert out[0]["fit"] == [{"text": "Độ ồn: yên tĩnh", "mentions": 3, "quote": None, "feature": "noise"}]


def test_unknown_is_not_penalised_but_evidence_against_a_wish_is():
    loud = stay("loud", 1, features={"noise": "loud"})
    blank = stay("blank", 1)
    d = trip(soft=[QUIET, {**QUIET, "feature": "steep_or_stairs", "value": "present", "weight": -1.0}])
    stairs = stay("stairs", 1, features={"steep_or_stairs": "present"})
    out = {c["id"]: c["score"] for c in rank([from_(loud), from_(blank), from_(stairs)], d, {}, CFG)}
    assert out["blank"] > out["stairs"]  # avoided and confirmed: a minus
    assert out["blank"] == out["loud"]    # another value than the loved one is no evidence against it


def from_(r):
    from planning.lodging import from_record
    return from_record(r)


def test_who_travels_along_counts_as_a_wish():
    d = trip(soft=[])
    d["trip_context"]["context"]["companions"] = ["kids"]
    kid = stay("kid", 1, features={"kids": "suitable"})
    out = rank([from_(kid), from_(stay("other", 1))], d, {}, CFG, LABELS)
    assert out[0]["id"] == "kid" and out[0]["fit"][0]["text"] == "Hợp trẻ em"


def test_a_hard_filter_drops_on_evidence_and_keeps_the_unverified():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present"}]
    cfg = CFG.__class__(**{**CFG.__dict__, "stay_min": 2})
    stays = [stay("stairs", 1, features={"steep_or_stairs": "present"}), stay("flat", 2), stay("level", 3)]
    out = candidates(places(), trip(hard=hard), cfg, None, None, stays)
    assert {c["id"] for c in out} == {"flat", "level"}
    assert all(c["unverified"] == ["steep_or_stairs"] for c in out)


def test_a_late_live_price_keeps_the_order_unless_it_breaks_the_cap():
    shown = [{**from_(stay(f"s{i}", i, price=400000)), "score": 3 - i} for i in range(3)]
    cards = [{"id": "s0", "price_vnd": 2_000_000, "price_source": "gmaps", "price_at": "t"},
             {"id": "s2", "price_vnd": 300_000, "price_source": "gmaps", "price_at": "t"}]
    out = refresh_prices(shown, cards, cap=1_000_000)
    assert [c["id"] for c in out] == ["s0", "s1", "s2"]
    assert out[0]["over_cap"] and out[0]["price_vnd"] == 2_000_000
    assert out[2]["price_vnd"] == 300_000 and not out[2]["over_cap"] and out[1]["price_vnd"] == 400000


def engine(recs, lodging_fn):
    return Engine(recs, cfg=CFG.__class__(**{**CFG.__dict__, "stay_min": 2}), live_cfg=FakeLive(), store=Store(None),
                  geocode_fn=no_geocode, matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30),
                  lodging_fn=lodging_fn, background=False, labels=LABELS)


def test_the_engine_ranks_served_stays_and_drops_one_whose_live_price_breaks_the_cap():
    d, recs = sample_trip(budget=4_000_000)  # 2 days -> 1 night: cap 1.2M
    d["trip_context"]["soft_weights"] = [QUIET]
    stays = [stay("s_quiet", 3, features={"noise": "quiet"}, price=500000), stay("s_plain", 0, price=500000)]

    def live_prices(center, radius_km, check_in, check_out, price_max, live_cfg):
        assert price_max is None  # the real price of every shown stay, even over the cap
        return [{"id": "s_plain", "name": "Stay s_plain", "lat": CENTRE[0], "lng": CENTRE[1], "rating": 4.0,
                 "reviews": 50, "price_vnd": 2_500_000, "amenities": [], "source": "gmaps", "fetched_at": "t"}]

    e = engine(recs + stays, live_prices)
    sid = e.create(d, None)["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert [c["id"] for c in lod["candidates"]] == ["s_quiet"]  # s_plain: its live price went over the cap
    (c,) = lod["candidates"]
    assert c["source"] == "corpus" and c["fit"] == [{"text": "Độ ồn: yên tĩnh", "mentions": 3, "quote": None}]
    assert c["avg_min"] is not None and c["price_vnd"] == 500000 and c["price_at"] is None


def test_a_booked_lodging_anchors_every_day_and_nothing_is_crawled():
    d, recs = sample_trip()
    hotel = {"place_id": None, "text": "Ana Mandara Villas", "lat": 11.9301, "lng": 108.4205, "province": None,
             "kind": "address"}
    d["trip_context"]["context"].update({"lodging_booked": "yes", "lodging": hotel})
    assert booked(d)["id"] == "@home" and with_booked_base(d)["trip_context"]["context"]["base"] == hotel
    e = engine(recs, lambda *a: pytest.fail("no lodging crawl for a booked trip"))
    out = e.create(d, None)
    assert out["view"]["lodging"] == {"status": "booked", "candidates": []}
    state = out["view"]["state"]
    assert state["lodging_touched"] and state["lodging_point"]["source"] == "user"
    assert (state["lodging_point"]["lat"], state["lodging_point"]["lng"]) == (11.9301, 108.4205)
    sid = out["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    first = e.load(sid)["view"]["itinerary"][0]["items"][0]
    assert first["kind"] == "travel" and first["from"] == "@home"  # the day leaves from the hotel
    assert e.lodging(sid)["status"] == "booked"


def test_a_base_with_a_point_needs_no_geocoding():
    pt, why = resolve_point({"place_id": None, "text": "Ana Mandara", "lat": 11.93, "lng": 108.42}, {},
                            lambda t: pytest.fail("no geocoding"))
    assert why is None and (pt.lat, pt.lng, pt.source) == (11.93, 108.42, "user")
