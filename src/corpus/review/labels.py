"""Gold labels for review observations: data/review/labels.jsonl, append-only; the latest label per observation wins.

A person reads the review text next to what the Extractor claimed and says correct / wrong / unsure. The labels give
the precision per (feature, value) that docs/specs/CORPUS_SPEC.md §Đo chất lượng asks for; a value whose measured
precision is below the gate is not served by itself. They never edit observations.

A label judges what a person can read: this review, this feature and value, these quoted words. It is keyed by that
content (`key`), not by the observation id, so it survives a re-run of observe with another prompt or model: a new
observation with the same review, feature, value and quote is already labelled; one the new run no longer makes
drops out of the statistics. Observations of any ontology version count while their value is still in the ontology.
"""

import collections
import json
import math
import os
import random
import re
import unicodedata

from ..crawl.common.files import append_jsonl, data_dir, now
from ..ontology import load as load_ontology

LABELS = ("correct", "wrong", "unsure")
GATE_MIN_N = 30  # labelled (correct + wrong) before a value can pass
GATE_LOWER = 0.8  # Wilson lower bound of the precision must reach this
SOURCE = "gmaps_review"  # rule-made observations (details, attributes) are not model output

_index: dict = {"key": None, "rows": []}


def _file():
    return data_dir() / "review" / "labels.jsonl"


def _all() -> list[dict]:
    f = _file()
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip().casefold()


def key(source_id: str, feature: str, value: str, quote: str) -> str:
    return "|".join((source_id, feature, value, _norm(quote)))


def latest() -> dict[str, dict]:
    """content key -> latest label. Records written before labels kept their quote are keyed through the current
    observations by id (migrate() writes the key into them once)."""
    by_id = {r[1]: r[4] for r in _rows()}
    out = {}
    for rec in _all():
        k = rec.get("key") or by_id.get(rec["id"])
        if k:
            out[k] = rec
    return out


def _rows() -> list[tuple]:
    """(file stem, observation id, feature, value, key) of every review observation whose value the ontology still
    has, cached until an observation file changes."""
    root = data_dir() / "gmaps" / "observations"
    files = sorted(root.glob("*.json")) if root.exists() else []
    stamp = (len(files), max((os.stat(f).st_mtime_ns for f in files), default=0))
    if _index["key"] != stamp:
        ont, rows = load_ontology(), []
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            rows += [(f.stem, o["id"], o["feature"], o["value"], key(o["source_id"], o["feature"], o["value"],
                                                                     o["span"]["quote"]))
                     for o in doc["observations"] if o["source_type"] == SOURCE and ont.valid(o["feature"], o["value"])]
        _index.update(key=stamp, rows=rows)
    return _index["rows"]


def migrate() -> int:
    """Write the content key and quote into label records that lack them, resolved through the current observation
    files. Run before observe is re-run (afterwards the ids may point at other content). Returns records changed."""
    by_id = {r[1]: r for r in _rows()}
    recs, changed = _all(), 0
    for rec in recs:
        row = by_id.get(rec["id"])
        if "key" not in rec and row:
            rec["key"] = row[4]
            rec["quote"] = row[4].split("|", 3)[3]
            changed += 1
    if changed:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        tmp.replace(_file())
    return changed


def _review_text(stem: str, review_id: str) -> str:
    place = data_dir() / "gmaps" / "places" / stem
    for name in ("reviews.json", "reviews_relevant.json"):
        f = place / name
        if not f.exists():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        for r in doc["reviews"] if isinstance(doc, dict) else doc:
            if r["review_id"] == review_id:
                return r["text"]
    return ""


def _item(stem: str, obs_id: str) -> dict | None:
    doc = json.loads((data_dir() / "gmaps" / "observations" / f"{stem}.json").read_text(encoding="utf-8"))
    o = next((o for o in doc["observations"] if o["id"] == obs_id), None)
    if o is None:
        return None
    return {"id": obs_id, "place": doc["place_fid"], "placeName": doc.get("place_name"), "feature": o["feature"],
            "value": o["value"], "quote": o["span"]["quote"], "context": o["context"],
            "observedAt": o["observed_at"], "text": _review_text(stem, o["source_id"])}


def sample(n: int = 1, feature: str | None = None, seed: int | None = None) -> list[dict]:
    """Unlabelled observations, the least-labelled (feature, value) first so every value gets its sample."""
    done = latest()
    counts = collections.Counter((r["feature"], r["value"]) for r in done.values())
    pool, seen = collections.defaultdict(list), set()
    for stem, obs_id, feat, value, k in _rows():
        if k not in done and k not in seen and (feature is None or feat == feature):
            seen.add(k)  # the same claim twice in one review is one item
            pool[(feat, value)].append((stem, obs_id))
    rng, out = random.Random(seed), []
    for _ in range(n):
        live = [k for k, v in pool.items() if v]
        if not live:
            break
        key = min(live, key=lambda k: (counts[k], rng.random()))
        stem, obs_id = pool[key].pop(rng.randrange(len(pool[key])))
        item = _item(stem, obs_id)
        if item:
            out.append(item)
            counts[key] += 1  # the next pick of this call goes to another value
    return out


def label(id: str, label_: str, note: str = "") -> dict:
    if label_ not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    row = next((r for r in _rows() if r[1] == id), None)
    if row is None:
        raise ValueError(f"unknown observation {id}")
    rec = {"at": now(), "id": id, "key": row[4], "place": row[0], "feature": row[2], "value": row[3],
           "quote": row[4].split("|", 3)[3], "label": label_, "note": note}
    append_jsonl(_file(), rec)
    return rec


def wilson_lower(correct: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = correct / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def stats() -> dict:
    """Per (feature, value): labels, precision, Wilson lower bound and whether the value passes the gate."""
    rows = _rows()
    pool = collections.Counter((r[2], r[3]) for r in rows)
    current = {r[4] for r in rows}
    got = collections.defaultdict(collections.Counter)
    for k, rec in latest().items():
        if k in current:  # a label on a claim the current observations no longer make says nothing about them
            got[(rec["feature"], rec["value"])][rec["label"]] += 1
    rows = []
    for key in sorted(set(pool) | set(got)):
        c = got[key]
        n = c["correct"] + c["wrong"]
        lower = round(wilson_lower(c["correct"], n), 3)
        rows.append({"feature": key[0], "value": key[1], "observations": pool[key], "correct": c["correct"],
                     "wrong": c["wrong"], "unsure": c["unsure"], "precision": round(c["correct"] / n, 3) if n else None,
                     "lower": lower, "gate": n >= GATE_MIN_N and lower >= GATE_LOWER, "needed": max(0, GATE_MIN_N - n)})
    return {"gate": {"min_n": GATE_MIN_N, "lower": GATE_LOWER}, "rows": rows,
            "labelled": sum(r["correct"] + r["wrong"] + r["unsure"] for r in rows),
            "total": sum(pool.values())}
