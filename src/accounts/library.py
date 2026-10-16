"""An account's own library on the home page: saved places and themes, and what it opened recently (from events)."""

import re

ITEM = {"place": re.compile(r"[A-Za-z0-9:_.-]{1,80}"), "theme": re.compile(r"[a-z0-9_]{1,32}")}
SAVED_MAX = 500
RECENT_MAX = 12
# events that mean "opened": name -> (kind, prop holding the id)
OPENED = {"detail_open": ("place", "place_id"), "theme_open": ("theme", "theme")}


class Library:
    def __init__(self, pool):
        self.pool = pool

    def read(self, user_id: str) -> dict:
        with self.pool.connection() as conn:
            saved = conn.execute("SELECT kind, item_id, saved_at FROM saved_items WHERE user_id = %s "
                                 "ORDER BY saved_at DESC LIMIT %s", (user_id, SAVED_MAX)).fetchall()
            recent = conn.execute(
                "SELECT kind, item_id, max(at) AS at FROM (SELECT CASE name WHEN 'detail_open' THEN 'place' "
                "ELSE 'theme' END AS kind, CASE name WHEN 'detail_open' THEN props->>'place_id' ELSE props->>'theme' "
                "END AS item_id, at FROM events WHERE user_id = %s AND name = ANY(%s)) e WHERE item_id IS NOT NULL "
                "GROUP BY kind, item_id ORDER BY at DESC LIMIT %s", (user_id, list(OPENED), RECENT_MAX)).fetchall()
        return {"saved": [{"kind": r["kind"], "id": r["item_id"], "at": r["saved_at"].isoformat(timespec="seconds")}
                          for r in saved],
                "recent": [{"kind": r["kind"], "id": r["item_id"], "at": r["at"].isoformat(timespec="seconds")}
                           for r in recent]}

    def save(self, user_id: str, kind, item_id, on) -> dict:
        """Saves (on=True) or forgets one place or theme; saving twice keeps the first time."""
        if kind not in ITEM or not isinstance(item_id, str) or not ITEM[kind].fullmatch(item_id):
            raise ValueError("bad saved item")
        if not isinstance(on, bool):
            raise ValueError("on must be true or false")
        with self.pool.connection() as conn:
            if on:
                if conn.execute("SELECT count(*) AS n FROM saved_items WHERE user_id = %s", (user_id,)).fetchone()["n"] >= SAVED_MAX:
                    raise ValueError(f"at most {SAVED_MAX} saved items")
                conn.execute("INSERT INTO saved_items (user_id, kind, item_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                             (user_id, kind, item_id))
            else:
                conn.execute("DELETE FROM saved_items WHERE user_id = %s AND kind = %s AND item_id = %s",
                             (user_id, kind, item_id))
        return self.read(user_id)
