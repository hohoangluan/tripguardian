import pytest

from harness.events import EventLog
from test_dispatch import Tools, run

pytestmark = pytest.mark.pg


@pytest.fixture
def log(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    with ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True) as pool:
        with pool.connection() as conn:
            conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", ("a" * 32,))
        yield EventLog(pool, "v-test")


def rows(log, where="true"):
    with log.pool.connection() as conn:
        return conn.execute(f"SELECT * FROM events WHERE {where} ORDER BY id").fetchall()


def test_client_batches_keep_only_allowlisted_names_and_props(log, store_kind):
    stored = log.client([{"name": "card_impression", "journey_id": "0123456789ab",
                          "props": {"place_id": "p1", "group": "chill", "rank": 3, "email": "x@y.z"}},
                         {"name": "steal_cookies", "props": {}},
                         {"name": "page_view", "props": {"route": "/app", "note": {"deep": 1}}}], "a" * 32)
    assert stored == 2
    kept = rows(log)
    assert [r["name"] for r in kept] == ["card_impression", "page_view"]
    assert kept[0]["props"] == {"place_id": "p1", "group": "chill", "rank": 3} and kept[0]["source"] == "client"
    assert kept[1]["props"] == {"route": "/app"} and kept[0]["app_version"] == "v-test"
    with pytest.raises(ValueError):
        log.client([{"name": "page_view"}] * 51, "a" * 32)


def test_anonymous_batches_only_keep_landing_events(log, store_kind):
    assert log.client([{"name": "page_view", "props": {"route": "/"}}, {"name": "today_open"}], None) == 1
    assert rows(log)[0]["user_id"] is None


def test_server_events_name_stage_operation_action_with_latency_and_path(log, store_kind):
    import test_dispatch
    from harness import Harness
    tools = {s: Tools(s) for s in ("trip", "decision", "planning")}
    h = Harness(tools["trip"], tools["decision"], tools["planning"], test_dispatch.STORE(None), log)
    v = h.create(owner="a" * 32)
    v = run(h, v, "turn", "t1", {"kind": "show"})
    v = run(h, v, "advance", "t2")
    run(h, v, "act", "t3", {"type": "select", "place_id": "p1", "text": "never stored"})
    run(h, v, "act", "t3", {"type": "select", "place_id": "p1", "text": "never stored"})  # a replay is not counted
    h.read(v["id"], "decision", "why-not", {"place": "p9"}, "a" * 32)
    h.places("hồ xuân hương", "a" * 32)
    names = [r["name"] for r in rows(log)]
    assert names == ["journey.create", "trip.turn", "trip.advance", "decision.act.select", "why_not", "places.search"]
    turn, act = rows(log, "name = 'trip.turn'")[0], rows(log, "name = 'decision.act.select'")[0]
    assert turn["props"]["compiled"] is True and turn["props"]["revision"] == 1 and "latency_ms" in turn["props"]
    assert act["props"]["place_id"] == "p1" and "text" not in act["props"]
    assert {r["user_id"].hex for r in rows(log)} == {"a" * 32}


def test_failed_mutation_is_an_event_with_the_error(log, store_kind):
    import test_dispatch
    from harness import Conflict, Harness
    tools = {s: Tools(s) for s in ("trip", "decision", "planning")}
    h = Harness(tools["trip"], tools["decision"], tools["planning"], test_dispatch.STORE(None), log)
    v = h.create()
    with pytest.raises(Conflict):
        run(h, v, "advance", "too-early")
    assert rows(log, "name = 'trip.advance'")[0]["props"]["error"] == "Conflict"
