"""Read-only view of Place Intelligence for online use: data/intel/places + data/tiktok/place_filter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from corpus import category_group, load_ontology
from corpus.serving import dishes

from ..domain.text import squash


@dataclass(frozen=True)
class Known:
    value: str
    n: int
    by_context: dict[str, str | None]  # "time_of_day=morning" -> firm value or unknown
    status: str = "VERIFIED"


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    category: str | None
    lat: float | None
    lng: float | None
    hours: dict[str, tuple[tuple[str, str], ...]] | None
    known: dict[str, Known]  # served features only (enough reviews, not uncertain, not waiting for review)
    weight: int  # total evidence behind the record; ranking tie-break
    category_group: str | None = None
    usable_as: tuple[str, ...] = ()
    evidence_record: dict | None = None

    def requirement_record(self) -> dict:
        if self.evidence_record is not None:
            return self.evidence_record
        ont = load_ontology()
        rec = {"identity": {"category": self.category, "category_group": self.category_group},
               "usable_as": list(self.usable_as)}
        for fid, k in self.known.items():
            if fid in ont.features:
                rec.setdefault(ont.features[fid].group, {})[fid] = {
                    "value": k.value, "status": "VERIFIED", "distribution": {k.value: k.n}, "n": k.n}
        return rec

    def value(self, feature: str, context: tuple[tuple[str, str], ...] = ()) -> str | None:
        k = self.known.get(feature)
        if k is None:
            return None
        for key, v in context:
            context_key = f"{key}={v}"
            if context_key in k.by_context:
                return k.by_context[context_key]
        return k.value


@dataclass
class Catalog:
    places: tuple[Candidate, ...]
    video_place: dict[str, str] = field(default_factory=dict)
    release_id: str | None = None

    def __post_init__(self):
        self.places = tuple(self.places)
        self.by_id = {p.id: p for p in self.places}
        # names long enough that seeing one in the agent's text means it named a place
        self.name_keys = [(k, p.id) for p in self.places if len((k := squash(p.name)).split()) >= 3]
        self._counts: dict[str, int] = {}

    def count(self, key: str) -> int:
        """Places whose served value matches 'feature=value' (context suffix ignored)."""
        if key not in self._counts:
            feature, _, value = key.split("@")[0].partition("=")
            self._counts[key] = sum(1 for p in self.places if p.value(feature) == value)
        return self._counts[key]

    def _dish_index(self) -> tuple[list[dict], dict[bool, str]]:
        """Built once (the places do not change while serving): the records to search, and every dish text joined,
        folded and with accents kept, so a phrase no menu holds is ruled out without a scan."""
        cached = self.__dict__.get("_dish_index_cache")
        if cached is None or len(cached[0]) != len(self.places):
            records = [{**p.requirement_record(), "id": p.id,
                        "identity": {**p.requirement_record().get("identity", {}), "name": p.name}}
                       for p in self.places]
            texts = [t for r in records for t in
                     [x for d in (r.get("menu") or {}).get("dishes") or [] for x in (d["name"], d.get("name_en")) if x]
                     + [o.get("text") for o in (r.get("details") or {}).get("order") or [] if o.get("text")]]
            cached = records, {a: " | ".join(dishes.key_for(t, a) for t in texts) for a in (True, False)}
            self.__dict__["_dish_index_cache"] = cached
        return cached

    def dishes(self, query: str) -> list[dict]:
        records, joined = self._dish_index()
        wanted, accented = dishes.phrases(query)
        if not any(f" {w} " in f" {joined[accented]} " for w in wanted):
            return []
        return dishes.search(records, query, limit=len(records))

    def kinds(self, query: str) -> list[Candidate]:
        key = squash(query)
        cats = self.__dict__.get("_kind_cats")
        if cats is None or len(cats) != len(self.places):
            cats = [f" {squash(p.category or '')} " for p in self.places]
            self.__dict__["_kind_cats"] = cats
        return [p for p, c in zip(self.places, cats) if key and f" {key} " in c]

    @classmethod
    def from_records(cls, records: Iterable[dict], n_min: int, videos: dict[str, str] | None = None,
                     evidence: Mapping[str, dict] | None = None) -> Catalog:
        """Explicit serving evidence is authoritative; without it use the legacy intel adapter."""
        if evidence is not None:
            return cls._from_served(evidence.values(), n_min, videos)
        out = []
        ont = load_ontology()
        for r in records:
            known, total = {}, 0
            for fid, sig in (r.get("features") or {}).items():
                total += sig.get("n", 0)
                served = sig.get("n", 0) >= n_min and sig.get("status") == "signal" and not sig.get("needs_review")
                if served and sig.get("top_value"):
                    ctx = {k: max(d, key=d.get) for k, d in (sig.get("by_context") or {}).items() if d}
                    known[fid] = Known(sig["top_value"], sig["n"], ctx)
            ident = r.get("identity") or {}
            estimates = r.get("estimates") or {}
            group = category_group(ident.get("category"))
            ev = evidence.get(r["place_fid"]) if evidence is not None else None
            if ev is None:
                ev = {"identity": {"category": ident.get("category"),
                                   "category_group": estimates.get("category_group") or group["id"]},
                      "usable_as": estimates.get("usable_as_default", group["usable_as"])}
                for fid, sig in (r.get("features") or {}).items():
                    if fid not in ont.features or sig.get("needs_review") or sig.get("status") == "disabled":
                        continue
                    # Full corpus records use the same serving status/precision policy as Decision.
                    if "confidence" in sig and "observation_ids" in sig:
                        from corpus.serving import build
                        ev = build(r)
                        break
                    if fid in known:
                        ev.setdefault(ont.features[fid].group, {})[fid] = {
                            "value": sig["top_value"], "status": "VERIFIED", "n": sig["n"],
                            "distribution": sig.get("distribution") or {sig["top_value"]: sig["n"]}}
            ev = {**ev, **{k: r[k] for k in ("menu", "details") if k in r}}
            hours = (r.get("operation") or {}).get("hours")
            out.append(Candidate(
                id=r["place_fid"], name=r["place_name"], category=ident.get("category"),
                lat=ident.get("lat"), lng=ident.get("lng"),
                hours={d: tuple(tuple(w) for w in ws) for d, ws in hours.items()} if hours else None,
                known=known, weight=total, category_group=ev["identity"].get("category_group"),
                usable_as=tuple(ev.get("usable_as") or []), evidence_record=ev))
        return cls(tuple(out), dict(videos or {}))

    @classmethod
    def _from_served(cls, records: Iterable[dict], n_min: int, videos=None) -> Catalog:
        ont = load_ontology()
        out = []
        for rec in records:
            known, total = {}, 0
            for fid, definition in ont.features.items():
                sig = (rec.get(definition.group) or {}).get(fid)
                if not sig:
                    continue
                n = sig.get("n") or 0
                total += n
                value = sig.get("value")
                distribution = sig.get("distribution") or {}
                if (sig.get("status") not in ("VERIFIED", "OUTDATED") or n < n_min
                        or value is None or any(v != value and count > 0 for v, count in distribution.items())):
                    continue
                ctx = {key: (next(iter(d)) if len(d) == 1 and next(iter(d.values())) > 0 else None)
                       for key, d in (sig.get("by_context") or {}).items()}
                known[fid] = Known(value, n, ctx, sig["status"])
            ident = rec.get("identity") or {}
            hours = (rec.get("operation") or {}).get("hours")
            windows = hours.get("value") if hours and hours.get("status") in ("VERIFIED", "OUTDATED") else None
            out.append(Candidate(
                id=rec["id"], name=ident.get("name") or rec["id"], category=ident.get("category"),
                lat=ident.get("lat"), lng=ident.get("lng"),
                hours={day: tuple(tuple(w) for w in ws) for day, ws in windows.items()} if windows else None,
                known=known, weight=total, category_group=ident.get("category_group"),
                usable_as=tuple(rec.get("usable_as") or ()), evidence_record=rec))
        ids = {p.id for p in out}
        return cls(tuple(out), {video: pid for video, pid in (videos or {}).items() if pid in ids})

    @classmethod
    def from_snapshot(cls, region, n_min: int) -> Catalog:
        """Read only the serving records and eligible membership of one snapshot region."""
        return cls._from_served(region.records(), n_min, region.videos)

    @classmethod
    def load(cls, data: Path, n_min: int) -> Catalog:
        files = sorted((data / "intel" / "places").glob("*.json"))
        if not files:
            raise FileNotFoundError(f"no place records in {data / 'intel' / 'places'}: run python -m corpus aggregate")
        records = [json.loads(p.read_text(encoding="utf-8")) for p in files]
        videos: dict[str, str] = {}
        for p in sorted((data / "tiktok" / "place_filter").glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            vids = d.get("videos")
            for v in vids if isinstance(vids, list) else []:  # some files store a count
                if (v.get("llm") or {}).get("relevance") == "yes":
                    videos[str(v["video_id"])] = d["fid"]
        return cls.from_records(records, n_min, videos)
