"""Weekly clustering of what users wrote (docs/ANALYTICS.md §Insights): after-trip notes and free-text Trip turns of
the last 7 days, grouped by the Extractor role (corpus.llm INSIGHT_CLUSTER) into insight_clusters. Offline; needs the
writing role (DATABASE_URL). Only shown to Admin; nothing here touches the corpus."""

import asyncio
from datetime import date, timedelta

from psycopg.types.json import Jsonb

MAX_TEXTS = 200


def texts(pool, since: date) -> dict[str, list[str]]:
    with pool.connection() as conn:
        notes = [r["note"] for r in conn.execute(
            "SELECT note FROM feedback WHERE at >= %s AND length(trim(note)) >= 5 ORDER BY at DESC LIMIT %s",
            (since, MAX_TEXTS))]
        typed = [r["text"] for r in conn.execute(
            "SELECT t->>'text' AS text FROM journeys j, "
            "jsonb_array_elements(coalesce(j.envelope->'snapshots'->'trip'->'transcript', '[]')) t "
            "WHERE j.updated_at >= %s AND t->>'role' = 'user' AND t->>'kind' = 'text' AND length(t->>'text') >= 8 "
            "LIMIT %s", (since, MAX_TEXTS))]
    return {"feedback": notes, "free_text": typed}


def group(items: list[str], source: str, ask) -> list[dict]:
    """ask(source=..., texts=...) -> {"clusters": [{"label", "members"}]}; members outside the list are dropped."""
    if len(items) < 3:
        return []
    numbered = "\n".join(f"{i}. {t.strip()[:300]}" for i, t in enumerate(items, 1))
    out = []
    for c in ask(source=source, texts=numbered).get("clusters", []):
        members = sorted({m for m in c.get("members", []) if 1 <= m <= len(items)})
        if members and c.get("label", "").strip():
            out.append({"label": c["label"].strip(), "size": len(members), "examples": [items[m - 1] for m in members[:5]]})
    return out


def run(pool, ask=None, today: date | None = None) -> int:
    """One week's groups; rerunning the same week replaces them. Returns how many groups were stored."""
    week = (today or date.today()) - timedelta(days=(today or date.today()).weekday())
    if ask is None:
        from corpus.llm import INSIGHT_CLUSTER
        client, model = INSIGHT_CLUSTER.role.client()
        ask = lambda **f: asyncio.run(INSIGHT_CLUSTER.ask(client, model, **f))  # noqa: E731
    rows = []
    for source, items in texts(pool, week - timedelta(days=7)).items():
        rows += [(source, g) for g in group(items, "after-trip notes" if source == "feedback" else "wishes typed", ask)]
    with pool.connection() as conn:
        conn.execute("DELETE FROM insight_clusters WHERE week = %s", (week,))
        for source, g in rows:
            conn.execute("INSERT INTO insight_clusters (week, source, label, size, examples) VALUES (%s, %s, %s, %s, %s)",
                         (week, source, g["label"], g["size"], Jsonb(g["examples"])))
    return len(rows)
