from datetime import datetime, timedelta, UTC

import pytest
from psycopg.types.json import Jsonb

import analytics

pytestmark = pytest.mark.pg


@pytest.fixture
def pool(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    with ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True) as p:
        yield p


def put(pool, jid, *names, at=None, **props):
    at = at or datetime.now(UTC) - timedelta(hours=1)
    with pool.connection() as conn:
        conn.execute("INSERT INTO journeys (id, stage, revision, envelope, created_at, updated_at) "
                     "VALUES (%s, 'trip', 0, '{}', %s, %s) ON CONFLICT DO NOTHING", (jid, at, at))
        for i, name in enumerate(names):
            p = dict(props.get(name, {}))
            conn.execute("INSERT INTO events (at, journey_id, source, name, props, app_version) "
                         "VALUES (%s, %s, 'server', %s, %s, 'v1')", (at + timedelta(minutes=i), jid, name, Jsonb(p)))


def test_funnel_counts_each_step_once_per_journey_and_names_where_people_stop(pool):
    full = ("journey.create", "trip.turn", "trip.advance", "decision.act.select", "preview.ready", "decision.advance",
            "planning.confirm", "feedback.submit")
    compiled = {"trip.turn": {"compiled": True}}
    put(pool, "aaaaaaaaaaaa", *full, **compiled)
    put(pool, "bbbbbbbbbbbb", "journey.create", "trip.turn", "trip.turn", "trip.advance", "decision.act.drop",
        **compiled)
    put(pool, "cccccccccccc", "journey.create", "trip.turn")  # a turn that did not compile
    steps = {s["key"]: s for s in analytics.funnel(pool, {})["steps"]}
    assert [steps[k]["journeys"] for k in ("created", "compiled", "shortlist", "chose", "confirm", "feedback")] == \
        [3, 2, 2, 1, 1, 1]
    assert steps["compiled"]["kept"] == round(2 / 3, 3)
    assert steps["shortlist"]["stopped"] == 1 and steps["shortlist"]["last_before_stop"] == [("decision.act.drop", 1)]
    assert steps["created"]["last_before_stop"] == [("trip.turn", 1)]
    assert steps["shortlist"]["median_min"] == 2.5  # 2 min and 3 min after creation


def test_filters_and_errors(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", **{"journey.create": {"start_with": "must"}})
    put(pool, "bbbbbbbbbbbb", "journey.create", "trip.turn", **{"trip.turn": {"error": "Conflict"}})
    assert analytics.funnel(pool, {"start_with": "must"})["steps"][0]["journeys"] == 1
    assert analytics.funnel(pool, {"app_version": "nope"})["steps"][0]["journeys"] == 0
    assert analytics.funnel(pool, {})["steps"][1]["journeys"] == 0  # an errored turn reaches nothing
    assert [s["id"] for s in analytics.sessions(pool, {"error": "1"})] == ["bbbbbbbbbbbb"]
    with pytest.raises(ValueError):
        analytics.funnel(pool, {"from": "2026-10-09", "to": "2026-10-01"})


def test_decision_tab_counts(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", "decision.act.drop", "decision.act.drop", "decision.act.select",
        "page_more", "preview.failed", **{"decision.act.drop": {"reason": "far"}})
    out = analytics.decision(pool, {})
    assert {r["action"]: r["n"] for r in out["acts"]} == {"drop": 2, "select": 1}
    assert out["drop_reasons"] == [{"reason": "far", "n": 2}] and out["counts"]["page_more"] == 1
    assert out["previews"] == [{"status": "failed", "n": 1}]


def test_session_replay_and_today(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", at=datetime.now(UTC) - timedelta(minutes=5))
    one = analytics.session(pool, "aaaaaaaaaaaa")
    assert one["events"][0]["name"] == "journey.create" and one["trip_transcript"] == []
    with pytest.raises(KeyError):
        analytics.session(pool, "000000000000")
    assert analytics.today(pool)["journeys"] == 1


def test_a_guests_journey_is_readable_and_guests_are_counted_apart_from_new_users(pool):
    with pool.connection() as conn:
        guest = conn.execute("INSERT INTO users (role, display_name) VALUES ('guest', 'Khách') RETURNING id").fetchone()["id"]
        conn.execute("INSERT INTO users (email, role) VALUES ('a@example.com', 'user')")
        conn.execute("INSERT INTO journeys (id, user_id, stage, revision, envelope) VALUES ('gggggggggggg', %s, 'trip', 0, '{}')",
                     (guest,))
        conn.execute("INSERT INTO events (user_id, journey_id, source, name) VALUES (%s, 'gggggggggggg', 'server', 'journey.create')",
                     (guest,))
    assert [(s["id"], s["role"]) for s in analytics.sessions(pool, {})] == [("gggggggggggg", "guest")]
    assert analytics.session(pool, "gggggggggggg")["role"] == "guest"
    day = analytics.today(pool)
    assert (day["new_users"], day["guests"]) == (1, 1)
