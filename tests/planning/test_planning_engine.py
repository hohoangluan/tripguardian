import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip, small_trip

from planning.engine import Engine, NoSession
from planning.session import ActionError, Store


def engine(records=None, lodging_fn=fake_lodging):
    d, recs = sample_trip() if records is None else (None, None)
    return Engine([], cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                 sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lodging_fn)


def test_create_returns_variants_right_away_without_waiting_on_lodging():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lambda *a: pytest.fail("lodging must not block create"))
    out = e.create(d, None)
    assert out["id"] and out["view"]["ok"] and out["view"]["variants"]
    assert out["view"]["lodging"]["status"] == "pending"


def test_load_an_unknown_session_is_no_session():
    e = engine()
    with pytest.raises(NoSession):
        e.load("0" * 12)


def test_lodging_turns_ready_once_the_background_crawl_finishes():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)  # run synchronously in tests
    out = e.create(d, None)
    sid = out["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert {c["id"] for c in lod["candidates"]} == {"h1", "h2"}


@pytest.mark.xfail(reason="Engine.act lands in Task 6", strict=True)
def test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one():
    d, recs = sample_trip(budget=2_000_000)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    variants = e.variants(sid)
    e.act(sid, {"type": "pick_variant", "id": variants[0]["id"]})
    e.act(sid, {"type": "pick_lodging", "id": "h2"})            # 900k/night, affordable under a 2M budget trip
    e.act(sid, {"type": "set_lodging_budget", "max_per_night": 400000})
    lod = e.lodging(sid)
    assert {c["id"] for c in lod["candidates"]} == {"h1"}       # h2 dropped out of the fetched list ...
    assert e.load(sid)["view"]["state"]["lodging_id"] == "h2"   # ... but the chosen lodging did not silently change
    with pytest.raises(ActionError):
        e.act(sid, {"type": "pick_lodging", "id": "h2"})        # re-picking a candidate no longer offered is refused
