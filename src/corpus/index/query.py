"""The online, read-only side of corpus.index. Vector similarity is never evidence: these calls rank and group places,
they never filter one out on their own, and every hit points back to a real photo or span."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..crawl.common.files import data_dir
from .embedder import Embedder, config


@dataclass(frozen=True)
class PhotoHit:
    place_id: str
    score: float
    file: str
    author: str
    owner: bool
    source: str


@dataclass(frozen=True)
class SpanHit:
    place_id: str
    score: float
    observation_id: str
    quote: str
    features: tuple[str, ...]
    served: bool = True


@dataclass(frozen=True)
class SpanRow:
    place_id: str
    observation_id: str | None
    quote: str
    features: tuple[str, ...]
    observations: tuple[str, ...]
    source: str | None
    served: bool
    claims: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PlaceHit:
    place_id: str
    score: float
    photos: tuple[str, ...]  # the matching photos, best first
    authors: int


@dataclass(frozen=True)
class Cluster:
    id: str
    style: str | None        # the dominant style tag of its places, if one holds for enough of them
    places: tuple[str, ...]  # best first
    photos: tuple[tuple[str, str], ...]  # (place_id, file): one photo of each of the first places


@dataclass
class TextVec:
    """A text in both spaces: photo (SigLIP2 text tower) and span (bge-m3)."""
    photo: np.ndarray
    span: np.ndarray | None = None


@dataclass
class Index:
    version: str
    root: Path
    places: dict
    styles: dict
    photo_vecs: np.ndarray
    photo_rows: list[dict]
    cfg: dict = field(default_factory=config)
    _emb: Embedder | None = None
    _spans: tuple | None = None  # (vecs, rows, served_mask)
    _span_rows: tuple[SpanRow, ...] | None = None
    _place_vecs: dict | None = None
    _photo_idx: dict | None = None  # place_id -> (rows of others' photos, rows of all photos), built on first use
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def current_version(data: Path | None = None) -> str | None:
        if data is None:
            from ..releases import resolve
            data = resolve(data_dir())
        p = data / "index" / "current"
        return p.read_text(encoding="utf-8").strip() if p.exists() else None

    @classmethod
    def load(cls, version: str | None = None, data: Path | None = None) -> "Index":
        import lancedb
        if data is None:
            from ..releases import resolve
            data = resolve(data_dir())
        version = version or cls.current_version(data)
        if not version:
            raise FileNotFoundError("no corpus index: run `python -m corpus index`")
        root = data / "index" / version
        db = lancedb.connect(str(root))
        vecs, rows = _read(db, "photos")
        return cls(version=version, root=root, places=json.loads((root / "places.json").read_text(encoding="utf-8")),
                   styles=json.loads((root / "styles.json").read_text(encoding="utf-8")), photo_vecs=vecs,
                   photo_rows=rows)

    # ---------- embedding (nothing is stored) ----------

    @property
    def embedder(self) -> Embedder:
        with self._lock:
            if self._emb is None:
                self._emb = Embedder.shared(self.cfg)
            return self._emb

    def embed_text(self, text: str, spans: bool = False) -> TextVec:
        with self._lock:
            emb = self._emb or Embedder.shared(self.cfg)
            self._emb = emb
            return TextVec(photo=emb.image_text([text])[0], span=emb.text([text])[0] if spans else None)

    def embed_image(self, data: bytes) -> np.ndarray:
        with self._lock:
            emb = self._emb or Embedder.shared(self.cfg)
            self._emb = emb
            return emb.image([data])[0]

    # ---------- search ----------

    def search_photos(self, vec, k: int | None = None, within: set[str] | None = None) -> list[PhotoHit]:
        v = vec.photo if isinstance(vec, TextVec) else vec
        k = k or self.cfg["search"]["k_photos"]
        if not len(self.photo_rows):
            return []
        scores = self.photo_vecs @ v.astype(np.float32)
        if within is not None:
            mask = np.fromiter((r["place_id"] in within for r in self.photo_rows), bool, len(self.photo_rows))
            scores = np.where(mask, scores, -np.inf)
        top = np.argsort(-scores)[:k]
        return [PhotoHit(r["place_id"], float(scores[i]), r["file"], r["author"], bool(r["owner"]), r["source"])
                for i in top if np.isfinite(scores[i]) for r in (self.photo_rows[i],)]

    def _load_spans(self) -> tuple[np.ndarray, list[dict], np.ndarray]:
        """Lazy-load spans table -> (vecs, rows, served_mask). Thread-safe."""
        with self._lock:
            if self._spans is None:
                import lancedb
                vecs, rows = _read(lancedb.connect(str(self.root)), "spans")
                served = np.array([_bool(r.get("served", True)) for r in rows], dtype=bool)
                self._spans = (vecs, rows, served)
        return self._spans

    def span_rows(self) -> tuple[SpanRow, ...]:
        """Read saved, typed span metadata without raw source I/O."""
        def values(value):
            return json.loads(value) if isinstance(value, str) else value or []
        if self._span_rows is not None:
            return self._span_rows
        _, rows, served = self._load_spans()
        result = tuple(SpanRow(row["place_id"], row.get("observation_id"), row.get("quote", ""),
                             tuple(values(row.get("features"))),
                             tuple(values(row.get("observations"))) or (row.get("observation_id"),),
                             row.get("source"), bool(served[i]), tuple(values(row.get("claims"))))
                     for i, row in enumerate(rows))
        with self._lock:
            if self._span_rows is None:
                self._span_rows = result
        return self._span_rows

    def search_spans(self, vec: TextVec, k: int | None = None, within: set[str] | None = None,
                     served_only: bool = True) -> list[SpanHit]:
        """Search spans by bge-m3 text similarity.

        served_only=True (default): evidence lookup — only spans backing served features.
        served_only=False: vibe/semantic search — reads all structurally valid spans,
        including descriptive ones that don't prove a specific feature."""
        if vec.span is None:
            raise ValueError("embed_text(..., spans=True) first")
        k = k or self.cfg["search"]["k_spans"]
        vecs, rows, served = self._load_spans()
        if not len(rows):
            return []
        scores = vecs @ vec.span.astype(np.float32)
        if served_only:
            scores = np.where(served, scores, -np.inf)
        if within is not None:
            scores = np.where(np.fromiter((r["place_id"] in within for r in rows), bool, len(rows)), scores, -np.inf)
        top = np.argsort(-scores)[:k]
        return [SpanHit(r["place_id"], float(scores[i]), r["observation_id"], r["quote"],
                        tuple(json.loads(r["features"]) if isinstance(r["features"], str) else r["features"]),
                        served=bool(served[i]))
                for i in top if np.isfinite(scores[i]) for r in (rows[i],)]

    def places_by_photos(self, hits: list[PhotoHit], min_photos: int | None = None,
                         min_authors: int | None = None) -> list[PlaceHit]:
        """A place counts only through several matching photos from several posters (no lucky single match). Its
        score: the mean of its best photos, the business's own photos weighed down."""
        c = self.cfg["places_by_photos"]
        min_photos = c["min_photos"] if min_photos is None else min_photos
        min_authors = c["min_authors"] if min_authors is None else min_authors
        by: dict[str, list[PhotoHit]] = {}
        for h in hits:
            by.setdefault(h.place_id, []).append(h)
        out = []
        for pid, hs in by.items():
            authors = {h.author for h in hs}
            if len(hs) < min_photos or len(authors) < min_authors:
                continue
            w = sorted((h.score * (c["owner_weight"] if h.owner else 1.0) for h in hs), reverse=True)[:c["per_place"]]
            out.append(PlaceHit(pid, float(np.mean(w)), tuple(h.file for h in sorted(hs, key=lambda h: -h.score)),
                                len(authors)))
        return sorted(out, key=lambda p: -p.score)

    def place_vec(self, pid: str) -> np.ndarray | None:
        with self._lock:
            if self._place_vecs is None:
                acc: dict[str, list[int]] = {}
                for i, r in enumerate(self.photo_rows):
                    acc.setdefault(r["place_id"], []).append(i)
                pv = {}
                for p, idx in acc.items():
                    m = self.photo_vecs[idx].mean(axis=0)
                    pv[p] = m / max(float(np.linalg.norm(m)), 1e-8)
                self._place_vecs = pv
        return self._place_vecs.get(pid)

    def similar_places(self, place_id: str, k: int = 12, within: set[str] | None = None) -> list[PlaceHit]:
        """Nearest places by their photos, without the place itself or its near-duplicate group."""
        v = self.place_vec(place_id)
        if v is None:
            return []
        group = self.places.get(place_id, {}).get("near_duplicate_group")
        out = []
        for pid in self.places:
            if pid == place_id or (group and self.places[pid].get("near_duplicate_group") == group):
                continue
            if within is not None and pid not in within:
                continue
            pv = self.place_vec(pid)
            if pv is not None:
                out.append(PlaceHit(pid, float(pv @ v), (), 0))
        return sorted(out, key=lambda p: -p.score)[:k]

    def best_photo(self, pid: str, vec: np.ndarray | None = None) -> str | None:
        with self._lock:
            if self._photo_idx is None:  # one pass here instead of two over every photo on each call
                built: dict[str, tuple[list[int], list[int]]] = {}
                for i, r in enumerate(self.photo_rows):
                    others, every = built.setdefault(r["place_id"], ([], []))
                    every.append(i)
                    if not r["owner"]:
                        others.append(i)
                self._photo_idx = built
        others, every = self._photo_idx.get(pid, ([], []))
        idx = others or every
        if not idx:
            return None
        ref = vec if vec is not None else self.place_vec(pid)
        return self.photo_rows[max(idx, key=lambda i: float(self.photo_vecs[i] @ ref))]["file"]

    def clusters(self, place_ids: list[str], vec: np.ndarray | None = None, k_max: int | None = None) -> list[Cluster]:
        """The places grouped into a few look-alike kinds (k-means on their mean photo vectors), each with its best
        places, one photo of each, and the style tag most of them carry. Kinds below min_places are left out."""
        from sklearn.cluster import KMeans
        c = self.cfg["clusters"]
        k_max = k_max or c["k_max"]
        ids = [p for p in dict.fromkeys(place_ids) if self.place_vec(p) is not None]
        if len(ids) < 2 * c["min_places"]:
            return []
        X = np.stack([self.place_vec(p) for p in ids])
        k = max(2, min(k_max, len(ids) // c["min_places"]))
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
        out = []
        for lab in range(k):
            members = [p for p, l in zip(ids, labels) if l == lab]
            if len(members) < c["min_places"]:
                continue
            ref = vec if vec is not None else X[labels == lab].mean(axis=0)
            members.sort(key=lambda p: -float(self.place_vec(p) @ ref))
            out.append(Cluster(id=f"k{lab}", style=self.dominant_style(members), places=tuple(members),
                               photos=tuple((p, f) for p in members[:c["photos"]] if (f := self.best_photo(p, ref)))))
        out.sort(key=lambda x: -len(x.places))
        return [Cluster(id=f"k{i}", style=x.style, places=x.places, photos=x.photos) for i, x in enumerate(out)]

    # ---------- style tags (layer B) ----------

    def style_ids(self) -> list[str]:
        return [s["id"] for s in self.styles["styles"]]

    def style_label(self, sid: str) -> str:
        return next((s["label"] for s in self.styles["styles"] if s["id"] == sid), sid)

    def place_styles(self, pid: str) -> dict:
        return self.places.get(pid, {}).get("styles", {})

    def dominant_style(self, pids: list[str], share: float = 0.4) -> str | None:
        """The most specific tag carried by at least `share` of these places (a child beats its parent)."""
        counts: dict[str, int] = {}
        for p in pids:
            for t in self.place_styles(p):
                counts[t] = counts.get(t, 0) + 1
        ok = [t for t, n in counts.items() if n >= max(1, share * len(pids))]
        if not ok:
            return None
        children = [t for t in ok if any(s.get("parent") for s in self.styles["styles"] if s["id"] == t)]
        return max(children or ok, key=lambda t: counts[t])

    def with_style(self, sid: str) -> list[str]:
        return [p for p, d in self.places.items() if sid in d.get("styles", {})]


def _bool(v) -> bool:
    """Coerce a LanceDB/PyArrow value to bool: handles str 'true'/'false', None, and native bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() == "true"
    return bool(v) if v is not None else True  # missing column → legacy index, treat as served


def _read(db, name: str) -> tuple[np.ndarray, list[dict]]:
    if name not in db.table_names():
        return np.zeros((0, 1), np.float32), []
    t = db.open_table(name).to_arrow()
    col = t.column("vector").combine_chunks()
    d = col.type.list_size
    vecs = col.flatten().to_numpy(zero_copy_only=False).astype(np.float32).reshape(-1, d)
    rows = t.drop(["vector"]).to_pylist()
    return vecs, rows
