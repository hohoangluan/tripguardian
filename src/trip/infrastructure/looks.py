"""corpus.index for the Trip agent: a look ("vibe retro", a photo) -> real corpus places and their kinds. Loaded once in a
thread at start (the embedder needs ~30 s); until it is ready, or when there is no index, every call returns nothing and
the turn goes on without photos (docs/TRIP_UNDERSTANDING.md §18)."""

from __future__ import annotations

import threading

from ..domain.state import VibeKind
from .catalog import Catalog


class Looks:
    def __init__(self, catalog: Catalog, warm: bool = True, index=None):
        """index: a loaded corpus.index.Index (tests); None = load the current one in a thread."""
        self.catalog = catalog
        self._ix, self._error = index, None
        self._ready = threading.Event()
        if index is not None:
            self._ready.set()
        elif warm:
            threading.Thread(target=self._load, name="looks-load", daemon=True).start()
        else:
            self._ready.set()

    def _load(self) -> None:
        try:
            from corpus.index import Index
            ix = Index.load()
            ix.embed_text("khởi động")  # loads the embedder now, not on the user's first look
            self._ix = ix
        except Exception as e:  # no index yet, no GPU: looks are off, the rest of Trip is not
            self._error = f"{type(e).__name__}: {e}"
        finally:
            self._ready.set()

    def ready(self, wait_s: float = 0.0) -> bool:
        self._ready.wait(wait_s)
        return self._ix is not None

    @property
    def total(self) -> int:
        return len(self._ix.places) if self.ready() else 0

    def name(self, pid: str) -> str:
        c = self.catalog.by_id.get(pid)
        return c.name if c else (self._ix.places.get(pid, {}).get("name", pid) if self._ix else pid)

    def by_cues(self, cues: list[str], within: set[str] | None = None, wait_s: float = 20.0) -> tuple[list[str], object]:
        """-> (place ids best first, the query vector) for a description made of visible signs."""
        if not cues or not self.ready(wait_s):
            return [], None
        ix = self._ix
        vec = ix.embed_text(", ".join(cues))
        hits = [h for h in ix.search_photos(vec, within=within) if h.score >= ix.cfg["search"]["min_text_photo"]]
        return [p.place_id for p in ix.places_by_photos(hits)], vec.photo

    def kinds(self, place_ids: list[str], vec=None) -> list[VibeKind]:
        if not self.ready() or not place_ids:
            return []
        ix, out, seen = self._ix, [], set()
        for c in ix.clusters(place_ids, vec):
            label = ix.style_label(c.style) if c.style else ""
            if not label or label in seen:
                label = f"Kiểu như {self.name(c.places[0])}"
            seen.add(label)
            out.append(VibeKind(id=c.id, label=label, style=c.style, places=c.places[:60], photos=c.photos))
        return out

    def by_photo(self, data: bytes, within: set[str] | None = None, wait_s: float = 20.0):
        """-> (photo vector, PlaceHits best first, the place it shows or None). The photo is not kept."""
        if not self.ready(wait_s):
            return None, [], None
        ix = self._ix
        vec = ix.embed_image(data)
        hits = ix.search_photos(vec, within=within)
        places = ix.places_by_photos(hits, min_photos=1, min_authors=1)
        rule = ix.cfg["place_pick"]
        shows = None
        if places and hits and hits[0].score >= rule["min_score"] and hits[0].place_id == places[0].place_id \
                and (len(places) < 2 or places[0].score - places[1].score >= rule["margin"]):
            shows = places[0].place_id
        return vec, places, shows

    def similar(self, pid: str, within: set[str] | None = None, k: int = 40) -> list[str]:
        return [p.place_id for p in self._ix.similar_places(pid, k, within)] if self.ready() else []

    def best_photo(self, pid: str) -> str | None:
        return self._ix.best_photo(pid) if self.ready() else None

    def styles_of(self, pid: str) -> list[str]:
        return list(self._ix.place_styles(pid)) if self.ready() else []


def photo_cues(data: bytes) -> dict:
    """A user's photo -> {kind, cues}: the Extractor's reading of its visible signs (corpus.llm PHOTO_CUES). Nothing
    is stored; a failure is an empty reading."""
    import asyncio

    from corpus.llm import PHOTO_CUES

    async def go():
        client, model = PHOTO_CUES.role.client()
        try:
            return await PHOTO_CUES.ask(client.with_options(timeout=40, max_retries=0), model, images=[data])
        finally:
            await client.close()

    out = asyncio.run(go())
    return out if isinstance(out, dict) else {}
