"""Logistics lookups the user web makes before any Planning session exists (docs/AGENT_HARNESS.md): a place to
start from, a lodging by name. Planning owns Live Context, so the harness reaches live only through here.

Nothing here writes anything but live's own cache, and nothing is made up: a source that fails gives fewer rows.
"""

import unicodedata

import live

LIMIT = 6


def fold(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").casefold().split())


def matches(query: str, name: str) -> bool:
    """Every typed word starts a word of the name, accents and case aside ("ana man" -> "Ana Mandara Villas")."""
    words = fold(name).replace("-", " ").split()
    return all(any(w.startswith(q) for w in words) for q in fold(query).replace("-", " ").split())


class Logistics:
    def __init__(self, records: list[dict], live_cfg, geosearch_fn=None):
        self.stays = [r for r in records if r["identity"].get("category_group") == "stay"
                      and r["identity"].get("lat") is not None and r["identity"].get("lng") is not None]
        self.live_cfg = live_cfg
        self.geosearch_fn = geosearch_fn or (lambda q: live.geosearch(q, live_cfg, LIMIT))

    # ---------- /geo ----------

    def geo(self, q: str) -> list[dict]:
        """Up to six places for a search box; [] when the sources do not answer (the box says nothing was found)."""
        try:
            return self.geosearch_fn(q)[:LIMIT]
        except live.Unavailable:
            return []

    # ---------- /lodging/suggest ----------

    def lodging_suggest(self, q: str) -> list[dict]:
        """Our own lodgings only (served `stay` records, most reviewed first), matched by name on the spot. No geosearch:
        its addresses drifted out of the trip region ("Mường Thanh" -> Điện Biên Phủ)."""
        q = " ".join((q or "").split())
        if len(q) < 2:
            return []
        hits = sorted((r for r in self.stays if matches(q, r["identity"].get("name") or "")),
                      key=lambda r: -((r.get("provenance") or {}).get("voices") or 0))
        return [{"kind": "corpus", "id": r["id"], "text": r["identity"]["name"], "address": r["identity"].get("address"),
                 "rating": ((r.get("provenance") or {}).get("rating_trend") or {}).get("recent_mean"),
                 "lat": r["identity"]["lat"], "lng": r["identity"]["lng"]} for r in hits[:LIMIT]]
