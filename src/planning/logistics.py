"""Logistics lookups the user web makes before any Planning session exists (docs/AGENT_HARNESS.md): a place to
start from, a lodging by name. Planning owns Live Context, so the harness reaches live only through here.

Nothing here writes anything but live's own cache, and nothing is made up: a source that fails gives fewer rows.
"""

import unicodedata

import live

LIMIT = 6
TOP_MAX = 12  # cards offered before any place is chosen
TOP_MIN_VOICES = 10  # a stay nobody reviewed is not worth leading with
PRIOR_MEAN, PRIOR_VOICES = 4.0, 20  # smoothing of the rating by how many reviewers wrote it


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

    def lodging_suggest(self, q: str, top: int = 0) -> list[dict]:
        """Our own lodgings only (served `stay` records, most reviewed first), matched by name on the spot. No geosearch:
        its addresses drifted out of the trip region ("Mường Thanh" -> Điện Biên Phủ).
        top > 0 with no query: the best stays to show as cards before the user has chosen any place (a user with no
        lodging yet taps one instead of typing): rating smoothed by the number of reviewers, so a 5-star with 3
        reviews does not beat a 4.6 with 300. Every row carries what a card shows; a missing value stays None."""
        q = " ".join((q or "").split())
        if len(q) < 2:
            return [self._row(r) for r in self._best(top)] if top > 0 and not q else []
        hits = sorted((r for r in self.stays if matches(q, r["identity"].get("name") or "")),
                      key=lambda r: -((r.get("provenance") or {}).get("voices") or 0))
        return [self._row(r) for r in hits[:LIMIT]]

    def _best(self, n: int) -> list[dict]:
        def score(r: dict) -> float:
            prov = r.get("provenance") or {}
            v, mean = prov.get("voices") or 0, (prov.get("rating_trend") or {}).get("recent_mean")
            return (mean * v + PRIOR_MEAN * PRIOR_VOICES) / (v + PRIOR_VOICES) if mean else 0.0
        return sorted((r for r in self.stays if ((r.get("provenance") or {}).get("voices") or 0) >= TOP_MIN_VOICES), key=lambda r: -score(r))[:min(n, TOP_MAX)]

    @staticmethod
    def _row(r: dict) -> dict:
        night = (r.get("operation") or {}).get("price_per_night") or {}
        ident = r["identity"]
        return {"kind": "corpus", "id": r["id"], "text": ident["name"], "address": ident.get("address"),
                "rating": ((r.get("provenance") or {}).get("rating_trend") or {}).get("recent_mean"),
                "lat": ident["lat"], "lng": ident["lng"], "price_vnd": night.get("value"), "price_at": night.get("as_of"),
                "category": ident.get("category"), "area": ident.get("area"),
                "reviews": (r.get("provenance") or {}).get("voices") or 0}
