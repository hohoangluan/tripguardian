"""corpus.index for the Trip agent: a look ("vibe retro", a photo) -> real corpus places and their kinds. Loaded once in a
thread at start (the embedder needs ~30 s); until it is ready, or when there is no index, every call returns nothing and
the turn goes on without photos (docs/TRIP_UNDERSTANDING.md §18)."""

from __future__ import annotations

import threading
from pathlib import Path

from corpus.retrieval import RetrievalEngine

from ..domain.state import VibeKind
from .catalog import Catalog


class Looks:
    def __init__(self, catalog: Catalog, warm: bool = True, index=None, *, data_root: Path | None = None,
                 index_version: str | None = None, pinned: bool = False,
                 retrieval: RetrievalEngine | None = None):
        """index: a loaded corpus.index.Index (tests); None = load the current one in a thread."""
        self.retrieval = retrieval
        self.catalog = catalog
        self.data_root = data_root
        self.index_version, self.pinned = index_version, pinned
        self._ix, self._error = index, None
        self._scored: dict[tuple, list[tuple[str, float]]] = {}
        self._ready = threading.Event()
        if index is not None:
            self._ready.set()
        elif warm:
            threading.Thread(target=self._load, name="looks-load", daemon=True).start()
        else:
            self._ready.set()
        self.warmed = threading.Event()  # retrieval's encoders are loaded (set at once when there is nothing to warm)
        if warm and retrieval is not None:
            threading.Thread(target=self._warm_retrieval, name="looks-warm", daemon=True).start()
        else:
            self.warmed.set()

    def _warm_retrieval(self) -> None:
        """One search at start loads retrieval's text encoders (~70 s cold), not the first photo card a user waits on."""
        try:
            self.retrieval.semantic("khởi động", within={p.id for p in self.catalog.places[:5]}, mode="vibe", limit=1)
        except Exception as e:  # warming is best effort: a real search reports its own error
            self._error = self._error or f"warm: {type(e).__name__}: {e}"
        finally:
            self.warmed.set()

    def _load(self) -> None:
        try:
            from corpus.index import Index
            if self.pinned and self.index_version is None:
                raise FileNotFoundError("no semantic index in the pinned corpus binding")
            kwargs = {"version": self.index_version} if self.pinned else {}
            ix = Index.load(data=self.data_root, **kwargs)
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
        return len(set(self._ix.places) & set(self.catalog.by_id)) if self.ready() else 0

    def name(self, pid: str) -> str:
        c = self.catalog.by_id.get(pid)
        return c.name if c else pid

    def _scope(self, within=None) -> set[str]:
        ids = set(self.catalog.by_id)
        return ids if within is None else ids & set(within)

    def by_cues(self, cues: list[str], within: set[str] | None = None, wait_s: float = 20.0) -> tuple[list[str], object]:
        """-> (place ids best first, the query vector) for a description made of visible signs."""
        if cues and self.retrieval is not None:
            scope = self._scope(within)
            try:
                hits = self.retrieval.semantic(", ".join(cues), within=scope, mode="vibe")
            except (OSError, RuntimeError) as error:
                self._error = f"{type(error).__name__}: {error}"
                return [], None
            return list(dict.fromkeys(h.place_id for h in hits if h.place_id in scope)), None
        if not cues or not self.ready(wait_s):
            return [], None
        ix = self._ix
        vec = ix.embed_text(", ".join(cues))
        scope = self._scope(within)
        hits = [h for h in ix.search_photos(vec, within=scope)
                if h.place_id in scope and h.score >= ix.cfg["search"]["min_text_photo"]]
        return [p.place_id for p in ix.places_by_photos(hits) if p.place_id in scope], vec.photo

    def kinds(self, place_ids: list[str], vec=None) -> list[VibeKind]:
        if not self.ready() or not place_ids:
            return []
        ix, out, seen = self._ix, [], set()
        scope = self._scope(place_ids)
        if not scope:
            return []
        for c in ix.clusters([p for p in place_ids if p in scope], vec):
            places = [p for p in c.places if p in scope]
            if not places:
                continue
            label = ix.style_label(c.style) if c.style else ""
            if not label or label in seen:
                label = f"Kiểu như {self.name(places[0])}"
            seen.add(label)
            out.append(VibeKind(id=c.id, label=label, style=c.style, places=places[:60],
                                photos=tuple(p for p in c.photos if p[0] in set(places[:60]))))
        return out

    def scored_by_cues(self, cues: list[str], within: set[str] | None = None) -> list[tuple[str, float]]:
        """One score per real place, using its best matching photo (or retrieval's score). Kept per (cues, scope): the
        photo cards ask the same fixed variants over the same topic places for every user (~0.4 s each uncached)."""
        scope = self._scope(within)
        if not cues or not scope:
            return []
        key = (tuple(cues), frozenset(scope))
        if (kept := self._scored.get(key)) is not None:
            return kept
        out = self._score(cues, scope)
        if out:
            if len(self._scored) >= 512:
                self._scored.clear()
            self._scored[key] = out
        return out

    def kept_scores(self) -> dict:
        """The cached scores as plain data (scopes stored once each), for `python -m trip drills` to save."""
        scopes: dict[frozenset, str] = {}
        entries = []
        for (cues, scope), scores in self._scored.items():
            name = scopes.setdefault(scope, f"s{len(scopes)}")
            entries.append({"cues": list(cues), "scope": name, "scores": [[p, round(v, 5)] for p, v in scores]})
        return {"scopes": {name: sorted(scope) for scope, name in scopes.items()}, "entries": entries}

    def keep_scores(self, saved: dict) -> int:
        """Scores saved offline go straight into the cache; -> how many."""
        scopes = {name: frozenset(ids) for name, ids in saved.get("scopes", {}).items()}
        for e in saved.get("entries", []):
            self._scored[(tuple(e["cues"]), scopes[e["scope"]])] = [(p, float(v)) for p, v in e["scores"]]
        return len(saved.get("entries", []))

    def _score(self, cues: list[str], scope: set[str]) -> list[tuple[str, float]]:
        if self.retrieval is not None:
            try:
                hits = self.retrieval.semantic(", ".join(cues), within=scope, mode="vibe")
            except (OSError, RuntimeError) as error:
                self._error = f"{type(error).__name__}: {error}"
                return []
        elif self.ready():
            ix = self._ix
            vec = ix.embed_text(", ".join(cues))
            hits = [h for h in ix.search_photos(vec, within=scope)
                    if h.score >= ix.cfg["search"]["min_text_photo"]]
        else:
            return []
        scores = {}
        for hit in hits:
            if hit.place_id in scope:
                scores[hit.place_id] = max(scores.get(hit.place_id, float("-inf")), hit.score)
        return sorted(scores.items(), key=lambda item: -item[1])

    def by_photo(self, data: bytes, within: set[str] | None = None, wait_s: float = 20.0):
        """-> (photo vector, PlaceHits best first, the place it shows or None). The photo is not kept."""
        if not self.ready(wait_s):
            return None, [], None
        ix = self._ix
        vec = ix.embed_image(data)
        scope = self._scope(within)
        hits = [h for h in ix.search_photos(vec, within=scope) if h.place_id in scope]
        places = [p for p in ix.places_by_photos(hits, min_photos=1, min_authors=1) if p.place_id in scope]
        rule = ix.cfg["place_pick"]
        shows = None
        if places and hits and hits[0].score >= rule["min_score"] and hits[0].place_id == places[0].place_id \
                and (len(places) < 2 or places[0].score - places[1].score >= rule["margin"]):
            shows = places[0].place_id
        return vec, places, shows

    def similar(self, pid: str, within: set[str] | None = None, k: int = 40) -> list[str]:
        if not self.ready() or pid not in self.catalog.by_id:
            return []
        scope = self._scope(within)
        return [p.place_id for p in self._ix.similar_places(pid, k, scope) if p.place_id in scope]

    def best_photo(self, pid: str) -> str | None:
        return self._ix.best_photo(pid) if self.ready() and pid in self.catalog.by_id else None

    def styles_of(self, pid: str) -> list[str]:
        return list(self._ix.place_styles(pid)) if self.ready() and pid in self.catalog.by_id else []


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
