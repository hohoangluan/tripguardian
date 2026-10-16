"""Online read side of the snapshot: one Region per city, loaded once, read-only."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import orjson
import polars as pl
import pyarrow as pa

from ..crawl.common.files import data_dir
from ..serving.record import config
from .tables import tables

FIRM = ("VERIFIED", "OUTDATED")
HINT = "run python -m corpus snapshot"


@dataclass
class FeatureColumn:
    """One served feature for every place of a region, in Region.ids order."""
    value: list
    status: list
    n: list
    conf: np.ndarray
    dist: list  # tuple of distribution keys, or None
    exists: np.ndarray = field(init=False)
    firm: np.ndarray = field(init=False)
    uncertain: np.ndarray = field(init=False)

    def __post_init__(self):
        self.exists = np.array([v is not None for v in self.status], dtype=bool)
        self.firm = np.array([s in FIRM for s in self.status], dtype=bool)
        self.uncertain = np.array([s == "UNCERTAIN" for s in self.status], dtype=bool)

    def eq(self, v) -> np.ndarray:
        return np.array([x == v for x in self.value], dtype=bool)

    def has(self, v) -> np.ndarray:
        return np.array([d is not None and v in d for d in self.dist], dtype=bool)

    def only(self, v) -> np.ndarray:
        return np.array([d is not None and set(d) <= {v} for d in self.dist], dtype=bool)


class _ById(Mapping):
    def __init__(self, region):
        self._r = region

    def __getitem__(self, pid):
        rec = self._r.record(pid)
        if rec is None:
            raise KeyError(pid)
        return rec

    def __contains__(self, pid):
        return pid in self._r.index

    def __iter__(self):
        return iter(self._r.ids)

    def __len__(self):
        return len(self._r.ids)


class Region:
    def __init__(self, key: str, t: dict[str, pa.Table]):
        self.key = key
        self.places = pl.from_arrow(t["places"])
        self._features = pl.from_arrow(t["features"])
        self._ctx = pl.from_arrow(t["feature_ctx"])
        self._verdicts = pl.from_arrow(t["fit_verdicts"])
        self._json = t["records"].column("json").to_pylist() if t["records"].num_rows else []
        self._intel = t["intel"].column("json").to_pylist() if t["intel"].num_rows else []
        self.videos = dict(zip(t["videos"].column("video_id").to_pylist(), t["videos"].column("place_id").to_pylist()))
        self.ids = self.places["id"].to_list()
        self.index = {pid: i for i, pid in enumerate(self.ids)}
        self.stay = frozenset(self.places.filter(pl.col("is_stay"))["id"].to_list())
        self.sigs = {pid: frozenset(tuple(s.split("=", 1)) for s in sig)
                     for pid, sig in zip(self.ids, self.places["signature"].to_list())}
        self.by_id = _ById(self)
        self._parsed: dict[str, dict] = {}
        self._all: list[dict] | None = None
        self._cols: dict = {}

    @classmethod
    def from_records(cls, records, intel=None, videos=None, key: str = "test") -> "Region":
        return cls(key, tables(list(records), intel, videos))

    def warm(self) -> "Region":
        """Build the lazy columns a Place Decision run reads, so the first request does not pay for them."""
        from ..ontology import load as load_ontology
        ont = load_ontology()
        for fid in ont.features:
            self.feature(fid)
        for who in ont.companions:
            self.verdict(who)
        for name in ("area", "category_for", "category_group", "near_duplicate_group", "name"):
            self.column(name)
        self.light  # noqa: B018
        return self

    def column(self, name: str) -> list:
        if ("p", name) not in self._cols:
            self._cols[("p", name)] = self.places[name].to_list()
        return self._cols[("p", name)]

    @property
    def light(self) -> list[dict]:
        """Per place: what code needs of a record's kind without parsing it (diversify.pick, groups.mmr)."""
        if ("light",) not in self._cols:
            self._cols[("light",)] = [
                {"id": pid, "identity": {"category_group": g}, "usable_as": u, "near_duplicate_group": d}
                for pid, g, u, d in zip(self.ids, self.column("category_group"), self.column("usable_as"),
                                        self.column("near_duplicate_group"))]
        return self._cols[("light",)]

    def record(self, pid: str) -> dict | None:
        i = self.index.get(pid)
        if i is None:
            return None
        if pid not in self._parsed:
            self._parsed[pid] = orjson.loads(self._json[i])
        return self._parsed[pid]

    def records(self) -> list[dict]:
        if self._all is None:
            self._all = [self.record(pid) for pid in self.ids]
        return self._all

    def intel(self) -> list[dict]:
        return [orjson.loads(j) for j in self._intel]

    def feature(self, fid: str) -> FeatureColumn:
        if ("f", fid) not in self._cols:
            rows = {r["place_id"]: r for r in self._features.filter(pl.col("fid") == fid).iter_rows(named=True)}
            get = [rows.get(pid) for pid in self.ids]
            self._cols[("f", fid)] = FeatureColumn(
                value=[r and r["value"] for r in get], status=[r and r["status"] for r in get],
                n=[r and r["n"] for r in get],
                conf=np.array([(r["conf"] or 0.0) if r else 0.0 for r in get], dtype=np.float64),
                dist=[tuple(r["dist_values"]) if r else None for r in get])
        return self._cols[("f", fid)]

    def ctx_top(self, fid: str, ctx_key: str) -> list:
        if ("c", fid, ctx_key) not in self._cols:
            rows = dict(self._ctx.filter((pl.col("fid") == fid) & (pl.col("ctx_key") == ctx_key))
                        .select("place_id", "top").iter_rows())
            self._cols[("c", fid, ctx_key)] = [rows.get(pid) for pid in self.ids]
        return self._cols[("c", fid, ctx_key)]

    def verdict(self, who: str) -> tuple[list, list]:
        if ("v", who) not in self._cols:
            rows = {r["place_id"]: r for r in self._verdicts.filter(pl.col("who") == who).iter_rows(named=True)}
            self._cols[("v", who)] = ([rows[p]["value"] if p in rows else None for p in self.ids],
                                      [rows[p]["status"] if p in rows else None for p in self.ids])
        return self._cols[("v", who)]


class Snapshot:
    def __init__(self, root: Path, version: str):
        self.root, self.version = root, version
        self._regions: dict[str, Region] = {}

    @classmethod
    def open(cls, root: Path | None = None) -> "Snapshot":
        if root is None:
            from ..releases import resolve
            base = resolve() / "snapshot"
        else:
            base = root
        cur = base / "current"
        if not cur.exists():
            raise FileNotFoundError(f"no {cur}: {HINT}")
        version = cur.read_text(encoding="utf-8").strip()
        if not (base / version).is_dir():
            raise FileNotFoundError(f"{cur} names {version}, which is missing: {HINT}")
        return cls(base, version)

    def region(self, key: str | None = None) -> Region:
        key = key or config()["default_region"]
        if key not in self._regions:
            path = self.root / self.version / key
            if not path.is_dir():
                raise FileNotFoundError(f"snapshot {self.version} has no region {key!r}: {HINT} --city {key}")
            import lancedb  # imported here: it takes seconds, and only a process that reads a region needs it
            db = lancedb.connect(str(path))
            names = ("places", "features", "feature_ctx", "fit_verdicts", "records", "intel", "videos")
            self._regions[key] = Region(key, {n: db.open_table(n).to_arrow() for n in names})
        return self._regions[key]


_OPEN: dict[tuple[str, str], Snapshot] = {}


def shared(root: Path | None = None, *, version: str | None = None) -> Snapshot:
    """One Snapshot per process and version: Decision, Planning and Trip in one server share the regions."""
    if version is not None:
        if root is None or not version or Path(version).name != version or version in {".", ".."}:
            raise FileNotFoundError("no valid pinned snapshot version; explicit revalidation is required")
        if not (root / version).is_dir():
            raise FileNotFoundError(f"pinned snapshot {version} is missing: {HINT}")
        s = Snapshot(root, version)
    else:
        s = Snapshot.open(root)
    return _OPEN.setdefault((str(s.root), s.version), s)
