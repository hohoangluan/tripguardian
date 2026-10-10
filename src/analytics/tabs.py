"""Admin tabs beyond the funnel (docs/ANALYTICS.md §Chỉ số): Trip, Planning, Thực tế, Thông báo, Agent, Chất lượng,
the Insights list and per-place demand. Read-only; every number says what it is counted over."""

import statistics
from datetime import timedelta

from .queries import _journeys, _range, decision, sessions


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(q * len(v)))], 1)


def _rows(conn, sql: str, args=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def trip(pool, params: dict) -> dict:
    with pool.connection() as conn:
        ids = list(_journeys(conn, params))
        turns = _rows(conn, "SELECT journey_id, at, props FROM events WHERE journey_id = ANY(%s) AND name = 'trip.turn' "
                            "AND props->>'error' IS NULL ORDER BY at", (ids,))
        backs = _rows(conn, "SELECT name, count(*) AS n FROM events WHERE journey_id = ANY(%s) AND name IN "
                            "('decision.back', 'planning.back') GROUP BY 1", (ids,))
        refined = conn.execute("SELECT count(*) AS n FROM events WHERE journey_id = ANY(%s) AND name = 'decision.turn' "
                               "AND (props->>'refined')::boolean", (ids,)).fetchone()["n"]
        unmapped = _rows(conn, "SELECT lower(u->>'phrase') AS phrase, count(DISTINCT j.id) AS journeys FROM journeys j, "
                               "jsonb_array_elements(coalesce(j.envelope->'outputs'->'trip'->'unmapped', '[]')) u "
                               "WHERE j.id = ANY(%s) GROUP BY 1 ORDER BY 2 DESC LIMIT 20", (ids,))
    until: dict[str, int] = {}
    done: set[str] = set()
    kinds: dict[str, int] = {}
    exits: dict[tuple, int] = {}
    paths: dict[str, int] = {}
    for t in turns:
        j, p = t["journey_id"], t["props"]
        kinds[p.get("kind") or "?"] = kinds.get(p.get("kind") or "?", 0) + 1
        if p.get("exit"):
            key = (p.get("qid") or "?", p["exit"])
            exits[key] = exits.get(key, 0) + 1
        if p.get("path"):
            paths[p["path"]] = paths.get(p["path"], 0) + 1
        if j not in done:
            until[j] = until.get(j, 0) + 1
            if p.get("compiled"):
                done.add(j)
    to_compile = [until[j] for j in done]
    return {"journeys": len(ids), "turns": len(turns), "turns_to_compile_median": statistics.median(to_compile) if to_compile else None,
            "compiled": len(done), "kinds": kinds, "paths": paths,
            "exits": [{"qid": q, "exit": e, "n": n} for (q, e), n in sorted(exits.items(), key=lambda x: -x[1])],
            "backs": {r["name"]: r["n"] for r in backs}, "refined": refined, "unmapped": unmapped}


def planning(pool, params: dict) -> dict:
    with pool.connection() as conn:
        ids = list(_journeys(conn, params))
        acts = _rows(conn, "SELECT split_part(name, '.', 3) AS action, count(*) AS n FROM events WHERE journey_id = ANY(%s) "
                           "AND name LIKE 'planning.act.%%' AND props->>'error' IS NULL GROUP BY 1 ORDER BY 2 DESC", (ids,))
        variants = _rows(conn, "SELECT props->>'id' AS variant, count(*) AS n FROM events WHERE journey_id = ANY(%s) "
                               "AND name = 'planning.act.pick_variant' GROUP BY 1 ORDER BY 2 DESC", (ids,))
        robust = _rows(conn, "SELECT coalesce(props->>'robustness', '?') AS level, count(*) AS n FROM events "
                             "WHERE journey_id = ANY(%s) AND name = 'planning.confirm' GROUP BY 1", (ids,))
        firsts = _rows(conn, "SELECT journey_id, name, min(at) AS at FROM events WHERE journey_id = ANY(%s) AND name IN "
                             "('decision.advance', 'planning.confirm', 'planning.back', 'planning.recommend') "
                             "AND props->>'error' IS NULL AND NOT props ? 'imported' GROUP BY 1, 2", (ids,))
        errors = conn.execute("SELECT count(*) AS n FROM events WHERE journey_id = ANY(%s) AND name LIKE 'planning.%%' "
                              "AND props ? 'error'", (ids,)).fetchone()["n"]
    by: dict[str, dict] = {}
    for r in firsts:
        by.setdefault(r["journey_id"], {})[r["name"]] = r["at"]
    entered = [j for j, x in by.items() if "decision.advance" in x]
    minutes = [(x["planning.confirm"] - x["decision.advance"]).total_seconds() / 60 for x in by.values()
               if "decision.advance" in x and "planning.confirm" in x]
    return {"entered": len(entered), "acts": acts, "variants": variants, "robustness": robust,
            "recommend_used": sum(1 for j in entered if "planning.recommend" in by[j]),
            "back_to_decision": sum(1 for j in entered if "planning.back" in by[j]),
            "advance_to_confirm_min": statistics.median(minutes) if minutes else None, "errors": errors}


def reality(pool, params: dict) -> dict:
    """Trips that have started. Every rate comes with its coverage: how many stops had any check-in at all."""
    start, end = _range(params)
    with pool.connection() as conn:
        stops = _rows(conn, "SELECT s.*, t.id AS trip FROM trip_stops s JOIN trips t ON t.id = s.trip_id "
                            "WHERE t.start_date IS NOT NULL AND t.start_date <= %s AND t.start_date >= %s "
                            "ORDER BY s.trip_id, s.day, s.seq", (end.date(), start.date() - timedelta(days=7)))
        off = conn.execute("SELECT count(*) AS n FROM checkins c JOIN trips t ON t.id = c.trip_id WHERE c.stop_id IS NULL "
                           "AND t.start_date <= %s AND t.start_date >= %s", (end.date(), start.date() - timedelta(days=7))).fetchone()["n"]
        counts = conn.execute("SELECT count(*) FILTER (WHERE name = 'companion.add') AS added, "
                              "count(*) FILTER (WHERE name = 'suggestion_open') AS opened FROM events "
                              "WHERE at >= %s AND at < %s", (start, end)).fetchone()
    status = {k: sum(1 for s in stops if s["status"] == k) for k in ("arrived", "skipped", "planned")}
    pairs = [(a, b) for a, b in zip(stops, stops[1:]) if a["trip"] == b["trip"]]
    after = [b["status"] == "arrived" for a, b in pairs if a["status"] == "arrived"]
    late = [(s["arrived_at"] - s["planned_arrive"]).total_seconds() / 60 for s in stops
            if s["status"] == "arrived" and s["arrived_at"] and s["planned_arrive"]]
    gaps = [((b["arrived_at"] - a["arrived_at"]) - (b["planned_arrive"] - a["planned_arrive"])).total_seconds() / 60
            for a, b in pairs if a["status"] == b["status"] == "arrived" and a["planned_arrive"] and b["planned_arrive"]
            and a["day"] == b["day"]]
    reasons: dict[str, int] = {}
    for s in stops:
        if s["status"] == "skipped":
            reasons[s["skip_reason"] or "không nói"] = reasons.get(s["skip_reason"] or "không nói", 0) + 1
    return {"stops": len(stops), "coverage": round(status["arrived"] / len(stops), 3) if stops else None,
            "status": status, "off_plan_checkins": off,
            "next_checkin_rate": round(sum(after) / len(after), 3) if after else None, "next_checkin_n": len(after),
            "late_min": {"median": _pct(late, 0.5), "p90": _pct(late, 0.9), "n": len(late)},
            "gap_vs_plan_min": {"median": _pct(gaps, 0.5), "n": len(gaps)}, "skip_reasons": reasons,
            "ratings": {"up": sum(1 for s in stops if s["rating"] == 1), "down": sum(1 for s in stops if s["rating"] == -1)},
            "added_from_suggestions": counts["added"], "suggestions_opened": counts["opened"]}


def notifications(pool, params: dict) -> dict:
    start, end = _range(params)
    with pool.connection() as conn:
        perm = _rows(conn, "SELECT props->>'result' AS result, count(*) AS n FROM events WHERE name = 'push_permission' "
                           "AND at >= %s AND at < %s GROUP BY 1", (start, end))
        by = _rows(conn, """
            SELECT n.kind, coalesce(n.variant, '?') AS variant, count(*) AS sent, count(n.opened_at) AS opened,
              count(*) FILTER (WHERE n.opened_at IS NOT NULL AND EXISTS (SELECT 1 FROM events e WHERE e.user_id = n.user_id
                AND e.source = 'server' AND e.at > n.opened_at AND e.at <= n.opened_at + interval '2 hours')) AS useful
            FROM notifications n WHERE n.status = 'sent' AND n.sent_at >= %s AND n.sent_at < %s GROUP BY 1, 2 ORDER BY 1, 2""",
                   (start, end))
        skipped = _rows(conn, "SELECT kind, skip_reason, count(*) AS n FROM notifications WHERE status = 'skipped' "
                              "AND scheduled_at >= %s AND scheduled_at < %s GROUP BY 1, 2 ORDER BY 3 DESC", (start, end))
        offs = conn.execute("SELECT count(*) AS n FROM events WHERE name = 'notify.prefs' AND at >= %s AND at < %s "
                            "AND ((props->>'paused')::boolean OR (props->>'kinds_off')::int > 0)", (start, end)).fetchone()["n"]
    sent = sum(r["sent"] for r in by)
    return {"permission": perm, "by_variant": by, "skipped": skipped, "sent": sent,
            "off_or_pause_per_1000": round(offs * 1000 / sent, 1) if sent else None}


def _decision_fallback(conn, params: dict) -> dict:
    """Typed chat turns of the Decision sessions of journeys in range, read from their own log: how many the agent
    answered and why the others fell back to keywords ("agent_fallback: first token too slow" -> "first token too
    slow"; an API error keeps only its type)."""
    ids = list(_journeys(conn, params))
    logs = _rows(conn, "SELECT l->'action'->'log' AS log FROM journeys j, "
                       "jsonb_array_elements(coalesce(j.envelope->'snapshots'->'decision'->'log', '[]')) l "
                       "WHERE j.id = ANY(%s) AND l->'action'->>'type' = 'turn'", (ids,))
    reasons: dict[str, int] = {}
    heuristic = 0
    for r in logs:
        lines = [x for x in (r["log"] or []) if isinstance(x, str)]
        if any(x.startswith("heuristic:") for x in lines):
            heuristic += 1
        fell = next((x for x in lines if x.startswith("agent_fallback")), None)
        if fell:
            why = fell.split(":", 1)[1].strip().split(":", 1)[0] or "?"
            reasons[why] = reasons.get(why, 0) + 1
    asked = len(logs) - heuristic  # an exact command never asks the agent
    fallback = sum(reasons.values())
    return {"turns": len(logs), "asked_agent": asked, "fallback": fallback,
            "rate": round(fallback / asked, 3) if asked else None,
            "reasons": dict(sorted(reasons.items(), key=lambda x: -x[1]))}


def agent(pool, params: dict) -> dict:
    """Per kind of model-backed request: count, latency, time to the first streamed event, fallback and errors.
    Per-call numbers of each model role are not recorded yet; these are the journey requests that use them.
    `decision_fallback`: the Decision chat's agent fallback rate and reasons from the session logs."""
    start, end = _range(params)
    with pool.connection() as conn:
        rows = _rows(conn, "SELECT name, props FROM events WHERE name IN ('trip.turn', 'decision.turn', 'planning.recommend') "
                           "AND at >= %s AND at < %s AND NOT props ? 'imported'", (start, end))
        decision_fallback = _decision_fallback(conn, params)
    out = []
    for name in ("trip.turn", "decision.turn", "planning.recommend"):
        mine = [r["props"] for r in rows if r["name"] == name]
        lat = [p["latency_ms"] for p in mine if isinstance(p.get("latency_ms"), (int, float))]
        first = [p["first_ms"] for p in mine if isinstance(p.get("first_ms"), (int, float))]
        errors: dict[str, int] = {}
        for p in mine:
            if p.get("error"):
                errors[p["error"]] = errors.get(p["error"], 0) + 1
        out.append({"name": name, "n": len(mine), "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95),
                    "first_event_p50_ms": _pct(first, 0.5),
                    "fallback_rate": round(sum(1 for p in mine if p.get("path") == "fallback") / len(mine), 3) if mine else None,
                    "heuristic": sum(1 for p in mine if str(p.get("path", "")).startswith("heuristic")), "errors": errors})
    return {"requests": out, "decision_fallback": decision_fallback}


def quality(pool, params: dict) -> dict:
    with pool.connection() as conn:
        created = _journeys(conn, params)
        ids = list(created)
        confirms = _rows(conn, "SELECT DISTINCT ON (journey_id) journey_id, at, props FROM events WHERE journey_id = ANY(%s) "
                               "AND name = 'planning.confirm' AND NOT props ? 'imported' ORDER BY journey_id, at", (ids,))
        previews = _rows(conn, "SELECT split_part(name, '.', 2) AS status, count(*) AS n FROM events WHERE journey_id = ANY(%s) "
                               "AND name IN ('preview.ready', 'preview.failed') GROUP BY 1", (ids,))
        away = conn.execute("SELECT count(*) FILTER (WHERE name = 'outbound_click') AS outbound, "
                            "count(*) FILTER (WHERE name = 'tab_hidden' AND props->>'stage' = 'decision') AS hidden "
                            "FROM events WHERE journey_id = ANY(%s)", (ids,)).fetchone()
    fails = sum(int((c["props"] or {}).get("hard_fail") or 0) for c in confirms)
    checks = sum(int((c["props"] or {}).get("hard_checks") or 0) for c in confirms)
    unknown = sum(int((c["props"] or {}).get("hard_unknown") or 0) for c in confirms)
    p = {r["status"]: r["n"] for r in previews}
    times = [(c["at"] - created[c["journey_id"]]).total_seconds() / 60 for c in confirms if c["journey_id"] in created]
    return {"confirmed": len(confirms), "hard_fail": fails, "alarm": fails > 0,
            "hard_unknown_rate": round(unknown / checks, 3) if checks else None,
            "feasible_rate": round(p.get("ready", 0) / (p.get("ready", 0) + p.get("failed", 0)), 3) if p else None,
            "time_to_plan_min": _pct(times, 0.5), "away": dict(away)}


def place(pool, pid: str, params: dict) -> dict:
    """Demand for one place (Admin Places, panel Nhu cầu): shown, opened, chosen, dropped (why), visited, rated."""
    start, end = _range(params)
    with pool.connection() as conn:
        ev = _rows(conn, "SELECT name, props->>'reason' AS reason, count(*) AS n FROM events WHERE at >= %s AND at < %s "
                         "AND props->>'place_id' = %s GROUP BY 1, 2", (start, end, pid))
        st = conn.execute("SELECT count(*) FILTER (WHERE status = 'arrived') AS arrived, "
                          "count(*) FILTER (WHERE status = 'skipped') AS skipped, count(*) FILTER (WHERE rating = 1) AS up, "
                          "count(*) FILTER (WHERE rating = -1) AS down, count(*) AS planned FROM trip_stops WHERE place_id = %s",
                          (pid,)).fetchone()
    count = lambda name: sum(r["n"] for r in ev if r["name"] == name)  # noqa: E731
    return {"impressions": count("card_impression"), "opened": count("detail_open"), "chosen": count("decision.act.select"),
            "dropped": count("decision.act.drop"), "drop_reasons": {r["reason"] or "không nói": r["n"] for r in ev
                                                                   if r["name"] == "decision.act.drop"},
            "why_not": count("why_not"), **dict(st)}


def insights(pool, params: dict) -> list[dict]:
    """Suggestions for a person to act on; nothing here writes the corpus."""
    out = []
    misses = decision(pool, params)["search_misses"]
    if misses:
        out.append({"kind": "search_miss", "title": "Từ khóa tìm không thấy", "action": "Thêm vào danh sách cần crawl",
                    "items": [{"label": m["q"], "n": m["n"]} for m in misses[:10]]})
    t = trip(pool, params)
    repeated = [u for u in t["unmapped"] if u["journeys"] >= 2]
    if repeated:
        out.append({"kind": "unmapped", "title": "Mong muốn lặp lại mà ontology chưa hiểu", "action": "Đề xuất thêm vào ontology",
                    "items": [{"label": u["phrase"], "n": u["journeys"]} for u in repeated[:10]]})
    start, end = _range(params)
    with pool.connection() as conn:
        dropped = _rows(conn, """
            SELECT props->>'place_id' AS place_id, count(*) FILTER (WHERE name = 'card_impression') AS shown,
              count(*) FILTER (WHERE name = 'decision.act.drop') AS dropped FROM events
            WHERE at >= %s AND at < %s AND name IN ('card_impression', 'decision.act.drop') AND props ? 'place_id'
            GROUP BY 1 HAVING count(*) FILTER (WHERE name = 'card_impression') >= 10
              AND count(*) FILTER (WHERE name = 'decision.act.drop') >= 0.3 * count(*) FILTER (WHERE name = 'card_impression')
            ORDER BY 3 DESC LIMIT 10""", (start, end))
    if dropped:
        out.append({"kind": "dropped_often", "title": "Hiện nhiều nhưng bị bỏ nhiều", "action": "Đưa vào hàng đợi duyệt",
                    "items": [{"label": d["place_id"], "n": d["dropped"], "of": d["shown"]} for d in dropped]})
    skipped = [e for e in t["exits"] if e["exit"] == "skip"]
    if skipped:
        out.append({"kind": "question_skipped", "title": "Câu hỏi Trip bị bỏ qua nhiều", "action": "Sửa config/trip.yaml",
                    "items": [{"label": e["qid"], "n": e["n"]} for e in skipped[:10]]})
    broken = sessions(pool, {**params, "error": "1"})
    if broken:
        out.append({"kind": "errors", "title": "Phiên có lỗi hoặc fallback", "action": "Mở Phiên chuyến đi",
                    "items": [{"label": s["id"], "n": s["errors"]} for s in broken[:10]]})
    return out


def clusters(pool) -> list[dict]:
    with pool.connection() as conn:
        return _rows(conn, "SELECT week, source, label, size, examples FROM insight_clusters "
                           "WHERE week = (SELECT max(week) FROM insight_clusters) ORDER BY source, size DESC")
