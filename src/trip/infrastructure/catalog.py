"""Read-only view of Place Intelligence for online use: data/intel/places + data/tiktok/place_filter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from corpus import category_group, load_ontology

from ..domain.text import squash


@dataclass(frozen=True)
class Known:
    value: str
    n: int
    by_context: dict[str, str]  # "time_of_day=morning" -> top value in that context


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
            hit = k.by_context.get(f"{key}={v}")
            if hit:
                return hit
        return k.value


@dataclass
class Catalog:
    places: tuple[Candidate, ...]
    video_place: dict[str, str] = field(default_factory=dict)

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

    @classmethod
    def from_records(cls, records: Iterable[dict], n_min: int, videos: dict[str, str] | None = None) -> Catalog:
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
            evidence = {"identity": {"category": ident.get("category"),
                                     "category_group": estimates.get("category_group") or group["id"]},
                        "usable_as": estimates.get("usable_as_default", group["usable_as"])}
            for fid, sig in (r.get("features") or {}).items():
                if fid not in ont.features or sig.get("needs_review") or sig.get("status") == "disabled":
                    continue
                # Full corpus records use the same serving status/precision policy as Decision.
                if "confidence" in sig and "observation_ids" in sig:
                    from corpus.serving import build
                    evidence = build(r)
                    break
                if fid in known:
                    evidence.setdefault(ont.features[fid].group, {})[fid] = {
                        "value": sig["top_value"], "status": "VERIFIED", "n": sig["n"],
                        "distribution": sig.get("distribution") or {sig["top_value"]: sig["n"]}}
            hours = (r.get("operation") or {}).get("hours")
            out.append(Candidate(
                id=r["place_fid"], name=r["place_name"], category=ident.get("category"),
                lat=ident.get("lat"), lng=ident.get("lng"),
                hours={d: tuple(tuple(w) for w in ws) for d, ws in hours.items()} if hours else None,
                known=known, weight=total, category_group=evidence["identity"].get("category_group"),
                usable_as=tuple(evidence.get("usable_as") or []), evidence_record=evidence))
        return cls(tuple(out), dict(videos or {}))

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
