"""Admin numbers read from Postgres with the read-only role (docs/ANALYTICS.md). Every function takes a pool whose
connections can only SELECT; nothing here writes."""

import statistics
from datetime import date, datetime, time, timedelta, timezone, UTC

# Funnel steps per journey: (key, label, event name, extra condition on props). Order is the product flow.
FUNNEL = (
    ("created", "Tạo hành trình", "journey.create", None),
    ("compiled", "Trip hiểu xong", "trip.turn", "compiled"),
    ("shortlist", "Thấy shortlist", "trip.advance", None),
    ("chose", "Chọn ≥ 1 nơi", "decision.act.select", None),
    ("preview", "Lịch xem trước sẵn sàng", "preview.ready", None),
    ("planning", "Vào Lịch trình", "decision.advance", None),
    ("confirm", "Chốt lịch", "planning.confirm", None),
    ("feedback", "Gửi phản hồi", "feedback.submit", None),
)
STAGES = ("trip", "decision", "planning")
FILTERS = ("from", "to", "start_with", "app_version")


def _range(params: dict) -> tuple[datetime, datetime]:
    """[from, to] as whole days in Asia/Ho_Chi_Minh (UTC+7); default the last 30 days."""
    tz = timezone(timedelta(hours=7))
    today = datetime.now(tz).date()
    start = date.fromisoformat(params["from"]) if params.get("from") else today - timedelta(days=29)
    end = date.fromisoformat(params["to"]) if params.get("to") else today
    if end < start:
        raise ValueError("to is before from")
    return datetime.combine(start, time(), tz), datetime.combine(end + timedelta(days=1), time(), tz)


def _journeys(conn, params: dict) -> dict[str, datetime]:
    """journey_id -> created time, for journeys created in the range that match start_with / app_version."""
    start, end = _range(params)
    sql = ("SELECT journey_id, min(at) AS at FROM events WHERE name = 'journey.create' AND at >= %s AND at < %s "
           "AND journey_id IS NOT NULL")
    args: list = [start, end]
    if params.get("start_with"):
        sql += " AND props->>'start_with' = %s"
        args.append(params["start_with"])
    if params.get("app_version"):
        sql += " AND app_version = %s"
        args.append(params["app_version"])
    return {r["journey_id"]: r["at"] for r in conn.execute(sql + " GROUP BY journey_id", args)}


def funnel(pool, params: dict) -> dict:
    """Journeys reaching each step, the share kept from the step before, minutes from creation (median, live
    journeys only) and, for journeys that stopped at a step, the most common last thing they did."""
    with pool.connection() as conn:
        created = _journeys(conn, params)
        ids = list(created)
        first: dict[str, dict[str, datetime]] = {j: {} for j in ids}
        last: dict[str, str] = {}
        imported: set[str] = set()  # milestones read back from saved state: their times are the file's, not real
        if ids:
            imported = {r["journey_id"] for r in conn.execute(
                "SELECT DISTINCT journey_id FROM events WHERE journey_id = ANY(%s) AND props ? 'imported'", (ids,))}
            for r in conn.execute(
                    "SELECT journey_id, name, (props->>'compiled') = 'true' AS compiled, min(at) AS at FROM events "
                    "WHERE journey_id = ANY(%s) AND props->>'error' IS NULL GROUP BY 1, 2, 3", (ids,)):
                key = next((k for k, _, name, cond in FUNNEL if name == r["name"] and (cond is None or r["compiled"])),
                           None)
                if key:
                    first[r["journey_id"]][key] = min(r["at"], first[r["journey_id"]].get(key, r["at"]))
            for r in conn.execute(
                    "SELECT DISTINCT ON (journey_id) journey_id, name FROM events WHERE journey_id = ANY(%s) "
                    "ORDER BY journey_id, at DESC, id DESC", (ids,)):
                last[r["journey_id"]] = r["name"]
        start, end = _range(params)
        top = conn.execute(
            "SELECT count(*) FILTER (WHERE name = 'page_view' AND props->>'route' = '/') AS landing, "
            "count(*) FILTER (WHERE name = 'landing_cta') AS cta, "
            "count(DISTINCT user_id) FILTER (WHERE name = 'auth.login') AS logins FROM events "
            "WHERE at >= %s AND at < %s", (start, end)).fetchone()
    steps, before = [], None
    for i, (key, label, _, _) in enumerate(FUNNEL):
        reached = [j for j in ids if key in first[j] or (key == "created")]
        minutes = [(first[j][key] - created[j]).total_seconds() / 60 for j in reached
                   if key in first[j] and j not in imported]
        later = {k for k, *_ in FUNNEL[i + 1:]}
        stopped = [j for j in reached if not later & set(first[j])]
        lasts: dict[str, int] = {}
        for j in stopped:
            lasts[last.get(j, "?")] = lasts.get(last.get(j, "?"), 0) + 1
        steps.append({"key": key, "label": label, "journeys": len(reached),
                      "kept": round(len(reached) / before, 3) if before else None,
                      "median_min": round(statistics.median(minutes), 1) if minutes else None,
                      "stopped": len(stopped) if i < len(FUNNEL) - 1 else 0,
                      "last_before_stop": sorted(lasts.items(), key=lambda x: -x[1])[:3] if i < len(FUNNEL) - 1 else []})
        before = len(reached) or before  # a step with no data yet (preview on imported journeys) is skipped
    return {"range": [d.isoformat() for d in _range(params)], "top": dict(top), "steps": steps}


def decision(pool, params: dict) -> dict:
    start, end = _range(params)
    with pool.connection() as conn:
        ids = list(_journeys(conn, params))

        def rows(sql, args=()):
            return [dict(r) for r in conn.execute(sql, (ids, *args))]
        acts = rows("SELECT split_part(name, '.', 3) AS action, count(*) AS n FROM events WHERE journey_id = ANY(%s) "
                    "AND name LIKE 'decision.act.%%' AND props->>'error' IS NULL GROUP BY 1 ORDER BY 2 DESC")
        reasons = rows("SELECT coalesce(props->>'reason', 'không nói') AS reason, count(*) AS n FROM events "
                       "WHERE journey_id = ANY(%s) AND name = 'decision.act.drop' GROUP BY 1 ORDER BY 2 DESC")
        previews = rows("SELECT split_part(name, '.', 2) AS status, count(*) AS n FROM events "
                        "WHERE journey_id = ANY(%s) AND name LIKE 'preview.%%' GROUP BY 1 ORDER BY 2 DESC")
        counts = conn.execute(
            "SELECT count(*) FILTER (WHERE name = 'page_more') AS page_more, "
            "count(*) FILTER (WHERE name = 'why_not') AS why_not, "
            "count(*) FILTER (WHERE name = 'compare_open') AS compare_open, "
            "count(*) FILTER (WHERE name = 'outbound_click') AS outbound_click FROM events "
            "WHERE journey_id = ANY(%s)", (ids,)).fetchone()
        # Rank of a selected place: the rank its card had when last shown before the select (impressions only as
        # the denominator; a card shown and not tapped says nothing about taste).
        ranks = rows(
            "SELECT (i.props->>'rank')::int AS rank, count(DISTINCT i.id) AS shown, count(DISTINCT s.id) AS chosen "
            "FROM events i LEFT JOIN events s ON s.journey_id = i.journey_id AND s.name = 'decision.act.select' "
            "AND s.props->>'place_id' = i.props->>'place_id' WHERE i.journey_id = ANY(%s) "
            "AND i.name = 'card_impression' AND i.props->>'rank' ~ '^[0-9]+$' GROUP BY 1 ORDER BY 1 LIMIT 30")
        misses = [dict(r) for r in conn.execute(
            "SELECT lower(props->>'q') AS q, count(*) AS n FROM events WHERE name = 'places.search' "
            "AND (props->>'hits')::int = 0 AND at >= %s AND at < %s GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
            (start, end))]
        edits = rows("SELECT count(*) AS n FROM events WHERE journey_id = ANY(%s) AND name LIKE 'decision.act.%%' "
                     "GROUP BY journey_id")
    per = [r["n"] for r in edits]
    return {"acts": acts, "drop_reasons": reasons, "previews": previews, "counts": dict(counts), "ranks": ranks,
            "search_misses": misses, "acts_per_journey_median": statistics.median(per) if per else None}


SESSION_FILTERS = {"reached", "abandoned", "low_feedback", "error"}


def sessions(pool, params: dict) -> list[dict]:
    """Journeys in the range, newest first; filters: reached=<stage>, abandoned=1 (quiet 24 h, never confirmed),
    low_feedback=1 (a score ≤ 2), error=1 (an event with an error or a fallback)."""
    start, end = _range(params)
    sql = """
        SELECT j.id, j.stage, j.revision, j.created_at, j.updated_at, j.app_version, u.email, u.display_name, u.role,
          (SELECT count(*) FROM events e WHERE e.journey_id = j.id AND (e.props ? 'error' OR e.props->>'path' = 'fallback')) AS errors,
          (SELECT min((v.value)::int) FROM feedback f, jsonb_each_text(f.scores) v WHERE f.journey_id = j.id) AS min_score,
          EXISTS (SELECT 1 FROM events e WHERE e.journey_id = j.id AND e.name = 'planning.confirm') AS confirmed,
          (SELECT e.props->>'start_with' FROM events e WHERE e.journey_id = j.id AND e.name = 'journey.create' LIMIT 1) AS start_with
        FROM journeys j LEFT JOIN users u ON u.id = j.user_id
        WHERE j.created_at >= %s AND j.created_at < %s"""
    args: list = [start, end]
    if params.get("app_version"):
        sql += " AND j.app_version = %s"
        args.append(params["app_version"])
    sql += " ORDER BY j.updated_at DESC LIMIT 500"
    with pool.connection() as conn:
        out = [dict(r) for r in conn.execute(sql, args)]
    now = datetime.now(UTC)
    if params.get("reached") in STAGES:
        out = [r for r in out if STAGES.index(r["stage"]) >= STAGES.index(params["reached"]) or r["confirmed"]]
    if params.get("abandoned"):
        out = [r for r in out if not r["confirmed"] and now - r["updated_at"] > timedelta(hours=24)]
    if params.get("low_feedback"):
        out = [r for r in out if r["min_score"] is not None and r["min_score"] <= 2]
    if params.get("error"):
        out = [r for r in out if r["errors"]]
    if params.get("start_with"):
        out = [r for r in out if r["start_with"] == params["start_with"]]
    return out


def session(pool, jid: str) -> dict:
    """One journey for replay: its saved envelope (transcripts, module logs, receipts), events and feedback."""
    with pool.connection() as conn:
        row = conn.execute("SELECT j.*, u.email, u.display_name, u.role FROM journeys j LEFT JOIN users u ON u.id = j.user_id "
                           "WHERE j.id = %s", (jid,)).fetchone()
        if not row:
            raise KeyError(jid)
        events = [dict(r) for r in conn.execute(
            "SELECT at, source, name, props, app_version FROM events WHERE journey_id = %s ORDER BY at, id", (jid,))]
        feedback = [dict(r) for r in conn.execute("SELECT at, scores, more_search, note FROM feedback "
                                                  "WHERE journey_id = %s ORDER BY at", (jid,))]
    env = row["envelope"] or {}
    snaps = env.get("snapshots") or {}
    return {"id": row["id"], "stage": row["stage"], "revision": row["revision"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "app_version": row["app_version"], "email": row["email"],
            "name": row["display_name"], "role": row["role"],
            "trip_transcript": (snaps.get("trip") or {}).get("transcript") or [],
            "decision_log": (snaps.get("decision") or {}).get("log") or [],
            "planning_log": (snaps.get("planning") or {}).get("log") or [],
            "receipts": [{"request_id": k, "at": v.get("at"), "revision": (v.get("response") or {}).get("revision"),
                          "stage": (v.get("response") or {}).get("stage"),
                          "events": [e.get("event") for e in v.get("events") or []]}
                         for k, v in (env.get("receipts") or {}).items()],
            "outputs": sorted((env.get("outputs") or {}).keys()),
            "events": events, "feedback": feedback}


def today(pool) -> dict:
    """The Dashboard row "Hôm nay" (Asia/Ho_Chi_Minh day)."""
    start, end = _range({})
    start = end - timedelta(days=1)
    with pool.connection() as conn:
        r = conn.execute(
            "SELECT count(*) FILTER (WHERE name = 'journey.create') AS journeys, "
            "count(*) FILTER (WHERE name = 'planning.confirm') AS confirmed, "
            "count(*) FILTER (WHERE name = 'feedback.submit') AS feedback, "
            "count(*) FILTER (WHERE props ? 'error') AS errors, "
            "count(*) FILTER (WHERE props->>'path' = 'fallback') AS fallbacks, "
            "count(DISTINCT user_id) AS active_users FROM events WHERE at >= %s AND at < %s", (start, end)).fetchone()
        new = conn.execute("SELECT count(*) FILTER (WHERE role <> 'guest') AS users, "
                           "count(*) FILTER (WHERE role = 'guest') AS guests FROM users "
                           "WHERE created_at >= %s AND created_at < %s AND deleted_at IS NULL", (start, end)).fetchone()
    return {**dict(r), "new_users": new["users"], "guests": new["guests"], "day": start.date().isoformat()}


def versions(pool) -> list[str]:
    with pool.connection() as conn:
        return [r["app_version"] for r in conn.execute(
            "SELECT app_version, max(at) AS last FROM events WHERE app_version IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")]
