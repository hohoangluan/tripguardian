import json

import pytest

from harness import Conflict, PgStore, import_files
from harness.contracts import Journey

pytestmark = pytest.mark.pg


@pytest.fixture
def pool(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    with ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True) as p:
        with p.connection() as conn:
            conn.execute("INSERT INTO users (id) VALUES (%s), (%s) ON CONFLICT DO NOTHING", ("a" * 32, "b" * 32))
        yield p


def test_a_second_writer_with_an_old_revision_gets_conflict(pool, store_kind):
    a, b = PgStore(pool, "v1"), PgStore(pool, "v1")
    j = a.new()
    a.save(j)
    first, second = a.get(j.id), b.get(j.id)
    first.revision += 1
    a.save(first)
    second.revision += 1
    with pytest.raises(Conflict):
        b.save(second)
    assert b.get(j.id).revision == 1  # the losing writer reloads the winner's journey


def test_journeys_list_by_owner_and_restart_reads_them_back(pool, store_kind):
    s = PgStore(pool, "v1")
    mine, other = s.new(), s.new()
    mine.user_id, other.user_id = "a" * 32, "b" * 32
    s.save(mine)
    s.save(other)
    assert s.list_for("a" * 32) == [mine.id]
    assert PgStore(pool).get(mine.id).user_id == "a" * 32
    with pool.connection() as conn:
        assert conn.execute("SELECT app_version FROM journeys WHERE id = %s", (mine.id,)).fetchone()["app_version"] == "v1"


def test_feedback_goes_to_the_table(pool, store_kind):
    PgStore(pool).append_feedback({"journey": "abc", "user_id": None, "at": "2026-10-08T07:20:47+00:00",
                                   "scores": {"fit": 4}, "more_search": None, "note": "ok"})
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM feedback").fetchone()
    assert row["scores"] == {"fit": 4} and row["note"] == "ok"


def test_import_files_is_idempotent(pool, tmp_path, store_kind):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for jid in ("0123456789ab", "ba9876543210"):
        (sessions / f"{jid}.json").write_text(Journey(id=jid, revision=3).model_dump_json())
    fb = tmp_path / "feedback.jsonl"
    fb.write_text(json.dumps({"journey": "0123456789ab", "at": "2026-10-08T07:20:47+00:00", "scores": {"fit": 4},
                              "more_search": None, "note": ""}) + "\n")
    assert import_files(pool, sessions, fb) == (2, 1)
    assert import_files(pool, sessions, fb) == (0, 0)
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM journeys WHERE user_id IS NULL").fetchone()["n"] == 2
    assert PgStore(pool).get("0123456789ab").revision == 3


def test_import_backfills_funnel_milestones_once(pool, tmp_path, store_kind):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    j = Journey(id="0123456789ab", stage="planning", sessions={"trip": "t", "decision": "d", "planning": "p"},
                outputs={"trip": {}, "planning": {}},
                snapshots={"decision": {"state": {"selected": ["x"]},
                                        "log": [{"action": {"type": "select"}, "at": "2026-10-08T01:02:03+00:00"}]}})
    (sessions / f"{j.id}.json").write_text(j.model_dump_json())
    (sessions / "ba9876543210.json").write_text(Journey(id="ba9876543210").model_dump_json())
    import_files(pool, sessions, None)
    import_files(pool, sessions, None)
    with pool.connection() as conn:
        got = [(r["journey_id"], r["name"]) for r in conn.execute("SELECT * FROM events ORDER BY id")]
        select_at = conn.execute("SELECT at FROM events WHERE name = 'decision.act.select'").fetchone()["at"]
    assert got == [("0123456789ab", n) for n in ("journey.create", "trip.turn", "trip.advance", "decision.act.select",
                                                 "decision.advance", "planning.confirm")] + \
        [("ba9876543210", "journey.create")]
    assert select_at.isoformat() == "2026-10-08T01:02:03+00:00"
