from datetime import date, datetime, timedelta, UTC

import pytest
from psycopg.types.json import Jsonb

import analytics
from analytics.cluster import run as cluster_run
from test_queries import pool, put  # noqa: F401  (fixture)

pytestmark = pytest.mark.pg
UID = "d" * 32


def test_trip_tab_counts_turns_to_compile_skips_and_unmapped(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", "trip.turn", "trip.turn", "trip.turn",
        **{"trip.turn": {"kind": "answer", "qid": "q_pace", "exit": "skip", "path": "agent"}})
    with pool.connection() as conn:  # the last turn compiled
        conn.execute("UPDATE events SET props = props || '{\"compiled\": true}' WHERE id = (SELECT max(id) FROM events)")
        conn.execute("UPDATE journeys SET envelope = %s", (Jsonb({"outputs": {"trip": {"unmapped": [{"phrase": "Xe Đạp Đôi"}]}}}),))
    put(pool, "bbbbbbbbbbbb", "journey.create")
    with pool.connection() as conn:
        conn.execute("UPDATE journeys SET envelope = %s WHERE id = 'bbbbbbbbbbbb'",
                     (Jsonb({"outputs": {"trip": {"unmapped": [{"phrase": "xe đạp đôi"}]}}}),))
    t = analytics.trip(pool, {})
    assert t["turns_to_compile_median"] == 3 and t["kinds"] == {"answer": 3} and t["paths"] == {"agent": 3}
    assert t["exits"] == [{"qid": "q_pace", "exit": "skip", "n": 3}]
    assert t["unmapped"] == [{"phrase": "xe đạp đôi", "journeys": 2}]
    kinds = {i["kind"] for i in analytics.insights(pool, {})}
    assert {"unmapped", "question_skipped"} <= kinds


def trip_with_stops(pool, statuses):
    now = datetime.now(UTC)
    with pool.connection() as conn:
        tid = conn.execute("INSERT INTO trips (journey_id, start_date, end_date, plan_hash) VALUES ('j1', %s, %s, 'h') "
                           "RETURNING id", (date.today(), date.today())).fetchone()["id"]
        for i, (status, late) in enumerate(statuses):
            planned = now - timedelta(hours=6 - i)
            conn.execute("INSERT INTO trip_stops (trip_id, day, seq, place_id, planned_arrive, planned_leave, status, "
                         "arrived_at, rating) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s)",
                         (tid, i + 1, f"p{i}", planned, planned + timedelta(minutes=50), status,
                          planned + timedelta(minutes=late) if status == "arrived" else None, 1 if i == 0 else None))


def test_reality_reports_next_checkin_rate_lateness_and_coverage(pool):
    trip_with_stops(pool, [("arrived", 10), ("arrived", 30), ("planned", 0), ("skipped", 0)])
    r = analytics.reality(pool, {})
    assert r["stops"] == 4 and r["coverage"] == 0.5 and r["status"] == {"arrived": 2, "skipped": 1, "planned": 1}
    assert r["next_checkin_rate"] == 0.5 and r["next_checkin_n"] == 2  # after stop 1 -> yes, after stop 2 -> no
    assert r["late_min"]["median"] == 30.0 and r["gap_vs_plan_min"]["median"] == 20.0 and r["ratings"]["up"] == 1


def test_notifications_tab_open_and_useful_rates_and_offs(pool):
    now = datetime.now(UTC)
    with pool.connection() as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s)", (UID,))
        for i, opened in enumerate([True, True, False]):
            conn.execute("INSERT INTO notifications (user_id, kind, variant, payload, scheduled_at, sent_at, opened_at, "
                         "status) VALUES (%s, 'day_brief', 'a', '{}', %s, %s, %s, 'sent')",
                         (UID, now - timedelta(hours=5 - i), now - timedelta(hours=5 - i),
                          now - timedelta(hours=5 - i) if opened else None))
        conn.execute("INSERT INTO events (at, user_id, source, name, props) VALUES (%s, %s, 'server', 'companion.checkin', '{}')",
                     (now - timedelta(hours=4, minutes=50), UID))
        conn.execute("INSERT INTO events (at, user_id, source, name, props) VALUES (%s, %s, 'server', 'notify.prefs', "
                     "'{\"paused\": true, \"kinds_off\": 0}')", (now, UID))
    n = analytics.notifications(pool, {})
    assert n["by_variant"] == [{"kind": "day_brief", "variant": "a", "sent": 3, "opened": 2, "useful": 1}]
    assert n["off_or_pause_per_1000"] == round(1000 / 3, 1)


def test_agent_and_quality(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", "trip.turn", "planning.confirm",
        **{"trip.turn": {"latency_ms": 900, "first_ms": 120, "path": "fallback"},
           "planning.confirm": {"hard_fail": 1, "hard_checks": 4, "hard_unknown": 2, "robustness": "fragile"}})
    a = {r["name"]: r for r in analytics.agent(pool, {})["requests"]}
    assert a["trip.turn"]["p50_ms"] == 900 and a["trip.turn"]["first_event_p50_ms"] == 120 and a["trip.turn"]["fallback_rate"] == 1
    q = analytics.quality(pool, {})
    assert q["alarm"] and q["hard_fail"] == 1 and q["hard_unknown_rate"] == 0.5 and q["confirmed"] == 1


def test_place_demand(pool):
    put(pool, "aaaaaaaaaaaa", "journey.create", "card_impression", "decision.act.drop",
        **{"card_impression": {"place_id": "px"}, "decision.act.drop": {"place_id": "px", "reason": "far"}})
    p = analytics.place(pool, "px", {})
    assert p["impressions"] == 1 and p["dropped"] == 1 and p["drop_reasons"] == {"far": 1} and p["arrived"] == 0


def test_cluster_job_stores_this_weeks_groups_and_replaces_on_rerun(pool):
    with pool.connection() as conn:
        for note in ("quán ồn quá", "muốn chỗ yên tĩnh hơn", "cần chỗ yên tĩnh để làm việc", "ok"):
            conn.execute("INSERT INTO feedback (journey_id, note, at) VALUES ('j', %s, now())", (note,))
    asked = []

    def ask(source, texts):
        asked.append(source)
        return {"clusters": [{"label": "muốn nơi yên tĩnh", "members": [2, 3, 99]}, {"label": " ", "members": [1]}]}
    assert cluster_run(pool, ask) == 1 and cluster_run(pool, ask) == 1
    rows = analytics.clusters(pool)
    assert len(rows) == 1 and rows[0]["size"] == 2 and rows[0]["source"] == "feedback" and asked == ["after-trip notes"] * 2


def test_agent_tab_reads_the_decision_agent_fallback_rate_and_reasons_from_session_logs(pool):
    def turn(*log):
        return {"version": 0, "action": {"type": "turn", "text": "x", "actions": [], "log": list(log)}, "scope": None}
    put(pool, "aaaaaaaaaaaa", "journey.create")
    logs = [turn(), turn("agent_fallback: first token too slow"), turn("agent_fallback: first token too slow"),
            turn("agent_fallback: bad plan: 1 validation error"), turn("heuristic:exact_command"),
            {"version": 1, "action": {"type": "select", "place_id": "p"}, "scope": None}]
    with pool.connection() as conn:
        conn.execute("UPDATE journeys SET envelope = %s", (Jsonb({"snapshots": {"decision": {"log": logs}}}),))
    d = analytics.agent(pool, {})["decision_fallback"]
    assert d == {"turns": 5, "asked_agent": 4, "fallback": 3, "rate": 0.75,
                 "reasons": {"first token too slow": 2, "bad plan": 1}}
