"""Gold labels for review observations: data/review/labels.jsonl, append-only; the latest label per observation wins.

A person reads the review text next to what the Extractor claimed and says correct / wrong / unsure. The labels give
the precision per (feature, value) that docs/CORPUS.md §Đo chất lượng asks for; a value whose measured
precision is below the gate is not served by itself. They never edit observations.

A label judges what a person can read: this review, this feature and value, these quoted words. It is keyed by that
content (`key`), not by the observation id, so it survives a re-run of observe with another prompt or model: a new
observation with the same review, feature, value and quote is already labelled; one the new run no longer makes
drops out of the statistics. Observations of any ontology version count while their value is still in the ontology.
"""

import ast
import collections
import json
import math
import os
import random
import re
import unicodedata
from pathlib import Path

from ..crawl.common.files import append_jsonl, data_dir, now
from ..ontology import load as load_ontology

LABELS = ("correct", "wrong", "unsure")
GATE_MIN_N = 30  # labelled (correct + wrong) before a value can pass
GATE_LOWER = 0.8  # Wilson lower bound of the precision must reach this
# model-made observations per source folder; rule-made ones (Maps details, attributes) are not labelled
SOURCES = {"gmaps": {"gmaps_review"}, "tiktok": {"tiktok_segment", "tiktok_caption", "tiktok_frame"},
           "gmaps_photo": {"gmaps_photo"}}
FOLDERS = {"gmaps": ("gmaps", "observations"), "tiktok": ("tiktok", "observations"),
           "gmaps_photo": ("gmaps", "photo_observations")}

_files: dict = {}  # observation file -> (mtime, its rows): a re-run rewrites files one by one


def _file():
    return data_dir() / "review" / "labels.jsonl"


def _judge_file():
    """Labels the Judge model wrote (corpus.judge): same records plus `by`; a person's label on the same claim wins."""
    return data_dir() / "review" / "judge_labels.jsonl"


def _read(f) -> list[dict]:
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


def _all() -> list[dict]:
    return _read(_judge_file()) + _read(_file())  # people last: the latest label per claim wins


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
    """(file stem, observation id, feature, value, key, source folder) of every model-made observation whose value
    the ontology still has; each file is read again only when it changed."""
    ont, rows, seen = load_ontology(), [], set()
    for source, types in SOURCES.items():
        root = data_dir().joinpath(*FOLDERS[source])
        for f in sorted(root.glob("*.json")) if root.exists() else []:
            seen.add(f)
            mtime = os.stat(f).st_mtime_ns
            if _files.get(f, (None,))[0] != mtime:
                doc = json.loads(f.read_text(encoding="utf-8"))
                _files[f] = (mtime, [(f.stem, o["id"], o["feature"], o["value"],
                                      key(o["source_id"], o["feature"], o["value"], o["span"]["quote"]), source)
                                     for o in doc["observations"] if o["source_type"] in types])
            rows += [r for r in _files[f][1] if ont.valid(r[2], r[3])]
    for f in set(_files) - seen:
        del _files[f]
    return rows


def migrate() -> int:
    """Write the content key and quote into label records that lack them, resolved through the current observation
    files. Run before observe is re-run (afterwards the ids may point at other content). Returns records changed."""
    by_id = {r[1]: r for r in _rows()}
    recs, changed = _read(_file()), 0  # people's file only; Judge labels always carry their key
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


OTHERS_MAX = 6  # other reviews of the same place on the same feature, shown next to the claim


def _reviews(stem: str) -> dict[str, dict]:
    """review_id -> review (with `list`: newest / relevant) of one place."""
    place, out = data_dir() / "gmaps" / "places" / stem, {}
    for name, kind in (("reviews.json", "newest"), ("reviews_relevant.json", "relevant")):
        f = place / name
        if not f.exists():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        for r in doc["reviews"] if isinstance(doc, dict) else doc:
            out.setdefault(r["review_id"], {**r, "list": kind})
    f = place / "reviews_extremes.json"
    if f.exists():
        doc = json.loads(f.read_text(encoding="utf-8"))
        for kind in ("lowest", "highest"):
            for r in doc.get(kind, {}).get("reviews", []):
                out.setdefault(r["review_id"], {**r, "list": kind})
    f = place / "reviews_keywords.json"
    if f.exists():
        for word, hits in json.loads(f.read_text(encoding="utf-8")).get("keywords", {}).items():
            for r in hits.get("reviews", []):
                out.setdefault(r["review_id"], {**r, "list": f"keyword:{word}"})
    return out


def _review_text(stem: str, review_id: str) -> str:
    return (_reviews(stem).get(review_id) or {}).get("text") or ""


def _as_list(v) -> list:
    """place.json keeps some lists as their Python repr ("['a', 'b']")."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("["):
        try:
            return list(ast.literal_eval(v))
        except (ValueError, SyntaxError):
            return [v]
    return [] if v in (None, "", "None") else [v]


def _review_card(r: dict) -> dict:
    return {"rating": r.get("rating"), "published": r.get("published_text"), "author": r.get("author_meta"),
            "details": [" ".join(str(d).split()) for d in _as_list(r.get("details"))], "likes": r.get("likes"),
            "photos": r.get("photos"), "list": r.get("list")}


def _video_card(v: dict, o: dict) -> tuple[str, dict]:
    """The words around a TikTok observation (the quoted segment and its neighbours, or the caption) and the video."""
    caption = " ".join([v.get("caption") or "", *(f"#{h}" for h in v.get("hashtags") or [])]).strip()
    segs = [s for s in (v.get("transcript") or {}).get("segments") or [] if (s.get("checked_text") or "").strip()]
    text = caption
    if o["source_type"] == "tiktok_segment" and o["span"].get("start_s") is not None:
        at = next((i for i, s in enumerate(segs) if s["start_s"] == o["span"]["start_s"]), None)
        if at is not None:
            text = " ".join(f"[{s['start_s']:.0f}s] {s['checked_text']}" for s in segs[max(0, at - 2): at + 3])
    frame = None
    if o["source_type"] == "tiktok_frame":
        n = round(o["span"]["start_s"] * 4 / max(1e-6, (v.get("transcript") or {}).get("total_s") or 1) + 0.5)
        frame = f"/api/labels/frame?video={v['video_id']}&n={max(1, min(4, n))}"
    return text, {"kind": "video", "url": v.get("video_url"), "caption": caption, "author": v.get("author_id"),
                  "published": o.get("observed_at"), "source": o["source_type"], "frame": frame,
                  "details": [], "rating": None, "likes": (v.get("stats") or {}).get("diggCount"), "photos": None,
                  "list": None}


def photo_path(stem: str, file: str) -> Path | None:
    f = data_dir() / "gmaps" / "places" / Path(stem).name / "photos" / Path(file).name
    return f if f.exists() else None


def frame_path(video_id: str, n: int) -> Path | None:
    f = data_dir() / "tiktok" / "videos" / Path(video_id).name / "frames" / f"f{int(n)}.jpg"
    return f if f.exists() else None


def _item(stem: str, obs_id: str, source: str = "gmaps") -> dict | None:
    doc = json.loads((data_dir().joinpath(*FOLDERS[source]) / f"{stem}.json").read_text(encoding="utf-8"))
    o = next((o for o in doc["observations"] if o["id"] == obs_id), None)
    if o is None:
        return None
    reviews = _reviews(stem)
    review = reviews.get(o["source_id"]) or {}
    text, card = review.get("text") or "", _review_card(review) if review else None
    if source == "gmaps_photo":
        text = f"Ảnh Maps: {o['span']['quote']}"
        card = {"kind": "video", "url": None, "caption": "", "author": o.get("author"), "published": o.get("observed_at"),
                "source": "gmaps_photo", "frame": f"/api/labels/photo?place={stem}&file={o['span']['field']}",
                "details": [], "rating": None, "likes": None, "photos": None, "list": None}
    if source == "tiktok":
        vf = data_dir() / "tiktok" / "videos" / o["source_id"] / "video.json"
        if vf.exists():
            text, card = _video_card(json.loads(vf.read_text(encoding="utf-8")), o)
    f = load_ontology().features.get(o["feature"])
    others = []  # what the rest of this place's evidence says on the same feature: agree, other value, rule-made
    for x in doc["observations"]:
        if x["feature"] != o["feature"] or x["id"] == obs_id or len(others) >= OTHERS_MAX:
            continue
        r = reviews.get(x["source_id"]) or {}
        others.append({"value": x["value"], "quote": x["span"]["quote"], "source": x["source_type"],
                       "rating": r.get("rating"), "published": r.get("published_text")})
    place_file = data_dir() / "gmaps" / "places" / stem / "place.json"
    place = json.loads(place_file.read_text(encoding="utf-8")) if place_file.exists() else {}
    return {"id": obs_id, "place": doc["place_fid"], "placeName": doc.get("place_name"), "feature": o["feature"],
            "value": o["value"], "quote": o["span"]["quote"], "context": o["context"],
            "observedAt": o["observed_at"], "text": text, "source": source,
            "definition": {"hint": f.hint if f else "", "claim": (f.claims.get(o["value"]) if f else None),
                           "values": list(f.values) if f else []},
            "review": card,
            "placeInfo": {k: place.get(k) for k in ("category", "address", "url", "rating", "review_count", "price",
                                                     "status", "description")}
                         | {"attributes": [str(a) for a in _as_list(place.get("attributes"))]},
            "others": others,
            "othersCount": {v: sum(1 for x in doc["observations"] if x["feature"] == o["feature"] and x["value"] == v)
                            for v in (f.values if f else ())}}


def sample(n: int = 1, feature: str | None = None, seed: int | None = None) -> list[dict]:
    """Unlabelled observations, the least-labelled (feature, value) first so every value gets its sample."""
    done = latest()
    counts = collections.Counter((r["feature"], r["value"]) for r in done.values())
    pool, seen = collections.defaultdict(list), set()
    for stem, obs_id, feat, value, k, source in _rows():
        if k not in done and k not in seen and (feature is None or feat == feature):
            seen.add(k)  # the same claim twice in one review is one item
            pool[(feat, value)].append((stem, obs_id, source))
    rng, out = random.Random(seed), []
    for _ in range(n):
        live = [k for k, v in pool.items() if v]
        if not live:
            break
        key = min(live, key=lambda k: (counts[k], rng.random()))
        stem, obs_id, source = pool[key].pop(rng.randrange(len(pool[key])))
        item = _item(stem, obs_id, source)
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
    rec = {"at": now(), "id": id, "key": row[4], "place": row[0], "source": row[5], "feature": row[2], "value": row[3],
           "quote": row[4].split("|", 3)[3], "label": label_, "note": note}
    append_jsonl(_file(), rec)
    return rec


def judge_label(obs: dict, place_stem: str, source: str, label_: str, note: str, by: str, ph: str = "",
                look: int = 1) -> dict:
    """A label written by the Judge model for one observation (obs: an observation record); ph = its prompt hash;
    look 2 = the strong Judge's second look at a claim the first Judge was unsure of."""
    if label_ not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    k = key(obs["source_id"], obs["feature"], obs["value"], obs["span"]["quote"])
    rec = {"at": now(), "id": obs["id"], "key": k, "place": place_stem, "source": source, "feature": obs["feature"],
           "value": obs["value"], "quote": k.split("|", 3)[3], "label": label_, "note": note, "by": by, "ph": ph}
    if look > 1:
        rec["look"] = look
    append_jsonl(_judge_file(), rec)
    return rec


def verdicts() -> dict[str, str]:
    """content key -> latest label (person over Judge): what aggregate drops (wrong, unsure_again) and counts as
    checked. unsure_again: the strong Judge's second look was still unsure, so the source is not enough evidence."""
    return {k: "unsure_again" if rec["label"] == "unsure" and rec.get("look", 1) > 1 else rec["label"]
            for k, rec in latest().items()}


def evidence(stem: str, o: dict, source: str) -> dict:
    """What the Judge reads for one observation: the passage around the quote (review text, transcript segments or
    caption, a photo's description), its date and rating, and the picture file for photos and frames."""
    out = {"text": "", "date": o.get("observed_at"), "rating": None, "image": None}
    if source == "gmaps":
        r = _reviews(stem).get(o["source_id"]) or {}
        text = " ".join((r.get("text") or "").split())
        at = text.casefold().find(" ".join(o["span"]["quote"].split()).casefold()[:40])
        lo = max(0, (at if at >= 0 else 0) - PASSAGE_CHARS // 2)
        out.update(text=text[lo: lo + PASSAGE_CHARS], rating=r.get("rating"))
    elif source == "gmaps_photo":
        out.update(text=f"photo, described by the small model as: {o['span']['quote']}",
                   image=photo_path(stem, o["span"]["field"]))
    else:
        vf = data_dir() / "tiktok" / "videos" / o["source_id"] / "video.json"
        v = json.loads(vf.read_text(encoding="utf-8")) if vf.exists() else {"video_id": o["source_id"]}
        text, card = _video_card(v, o)
        if o["source_type"] == "tiktok_frame":
            n = card["frame"].rsplit("=", 1)[1] if card.get("frame") else "1"
            out.update(text=f"video frame, described by the small model as: {o['span']['quote']}. Caption: {text}",
                       image=frame_path(o["source_id"], int(n)))
        else:
            out["text"] = f"TikTok {o['source_type'][7:]}: {text}"
    return out


PASSAGE_CHARS = 1500  # review text the Judge sees around a quote


def wilson_lower(correct: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = correct / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def stats() -> dict:
    """Per (feature, value): labels, precision, Wilson lower bound and whether the value passes the gate; by_source
    splits the correct / wrong counts per source folder (a new source has to earn its own precision)."""
    rows = _rows()
    pool = collections.Counter((r[2], r[3]) for r in rows)
    current = {r[4]: r[5] for r in rows}
    got = collections.defaultdict(collections.Counter)
    per_source = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for k, rec in latest().items():
        if k in current:  # a label on a claim the current observations no longer make says nothing about them
            got[(rec["feature"], rec["value"])][rec["label"]] += 1
            per_source[(rec["feature"], rec["value"])][current[k]][rec["label"]] += 1
    rows = []
    for key in sorted(set(pool) | set(got)):
        c = got[key]
        n = c["correct"] + c["wrong"]
        lower = round(wilson_lower(c["correct"], n), 3)
        rows.append({"feature": key[0], "value": key[1], "observations": pool[key], "correct": c["correct"],
                     "wrong": c["wrong"], "unsure": c["unsure"], "precision": round(c["correct"] / n, 3) if n else None,
                     "lower": lower, "gate": n >= GATE_MIN_N and lower >= GATE_LOWER, "needed": max(0, GATE_MIN_N - n),
                     "by_source": {src: {"correct": sc["correct"], "wrong": sc["wrong"]}
                                   for src, sc in sorted(per_source[key].items())}})
    return {"gate": {"min_n": GATE_MIN_N, "lower": GATE_LOWER}, "rows": rows,
            "labelled": sum(r["correct"] + r["wrong"] + r["unsure"] for r in rows),
            "total": sum(pool.values())}
