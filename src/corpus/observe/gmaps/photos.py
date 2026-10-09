"""gmaps photos observe: each place's crawled Maps photos -> data/gmaps/photo_observations/<fid_dir>.json.

The Extractor (corpus.llm.PHOTO_OBSERVE) reads a place's photos BATCH at a time and may only report PHOTO_VALUES:
what a still photo can prove (stairs, a dirt road, a packed crowd, indoor / outdoor, a view…), never an absence, a
quality, a price or who the place suits. Features with `check: span` are read again on their one photo
(PHOTO_VERIFY); only "supports" is kept. One vote per poster: author = the poster's author_hash (the same hash as
their reviews, so text and photo of one person count once); the business's own photos share one author per place.
observed_at = the month the photo was taken (else posted). A place is done again when its photos.json, the prompts,
PHOTO_VALUES or the ontology change; a failed place has no file this run and a line in
data/gmaps/photo_observe_errors.jsonl.
"""

import asyncio
import collections
import hashlib
import json
from pathlib import Path

from ...crawl.common.files import append_jsonl, data_dir, listed, load_config, now, safe_name, write_json
from ...llm import PHOTO_OBSERVE, PHOTO_VERIFY
from ...ontology import UNKNOWN, Ontology, load as load_ontology
from .. import CONTEXT_KEYS, keep_stale, observation

PHOTOS_FILE = "photos.json"  # written by corpus.crawl.gmaps.photos
OUT_DIR = "photo_observations"
BATCH = 4
PHOTO_VALUES = {
    "steep_or_stairs": {"present"}, "rough_road_access": {"present"}, "crowd": {"high"},
    "setting": {"indoor", "outdoor", "both"}, "scenic_view": {"present"}, "cloud_hunting": {"present"},
    "flower_garden": {"present"}, "nature": {"present"}, "outdoor_seating": {"present"}, "cozy_decor": {"present"},
    "camping": {"present"}, "animals": {"present"},
}
KEY = "|".join((PHOTO_OBSERVE.prompt_hash, PHOTO_VERIFY.prompt_hash, str(BATCH),
                json.dumps({k: sorted(v) for k, v in PHOTO_VALUES.items()}, sort_keys=True)))


def allowed_text(ont: Ontology) -> str:
    return "\n".join(f"- {f} = {' | '.join(sorted(vs))}: {ont.features[f].hint}" for f, vs in PHOTO_VALUES.items()
                     if f in ont.features)


def gate(answer: dict, n: int, ont: Ontology) -> tuple[list[dict], collections.Counter]:
    if not isinstance(answer, dict) or not isinstance(answer.get("observations"), list):
        raise ValueError("answer has no observations list")
    kept, dropped, seen = [], collections.Counter(), set()
    for o in answer["observations"]:
        f, v, i, q = o.get("feature"), o.get("value"), o.get("photo"), (o.get("quote") or "").strip()
        if not ont.valid(f, v) or v not in PHOTO_VALUES.get(f, ()):
            dropped["not_allowed"] += 1
        elif not isinstance(i, int) or not 1 <= i <= n:
            dropped["bad_photo"] += 1
        elif not q:
            dropped["no_quote"] += 1
        elif (f, v, i) in seen:
            dropped["duplicate"] += 1
        else:
            seen.add((f, v, i))
            kept.append({"feature": f, "value": v, "photo": i, "quote": q})
    values = collections.Counter((o["feature"], o["photo"]) for o in kept)
    mixed = {k for k, n in values.items() if n > 1}  # one photo, two values of one feature: the reader is unsure
    dropped["mixed_values"] += sum(values[k] for k in mixed)
    return [o for o in kept if (o["feature"], o["photo"]) not in mixed], +dropped


def _client():
    client, model = PHOTO_OBSERVE.role.client()
    return client.with_options(timeout=240, max_retries=0), model


async def observe_place(client, model: str, sem: asyncio.Semaphore, city: str, d: Path, ont: Ontology) -> dict:
    place = json.loads((d / "place.json").read_text(encoding="utf-8"))
    doc = json.loads((d / PHOTOS_FILE).read_text(encoding="utf-8"))
    photos = [p for p in doc["photos"] if (d / p["file"]).exists()]
    obs, dropped, seq = [], collections.Counter(), collections.Counter()
    for start in range(0, len(photos), BATCH):
        batch = photos[start:start + BATCH]
        images = [(d / p["file"]).read_bytes() for p in batch]
        listing = "; ".join(f"{i} = {'owner' if p['owner'] else 'visitor'} {p['kind']}, {p.get('month') or 'recent'}"
                            for i, p in enumerate(batch, 1))
        async with sem:
            answer = await PHOTO_OBSERVE.ask(client, model, images=images, city=city, count=len(batch),
                                             name=place.get("name"), category=place.get("category") or "unknown",
                                             photo_list=listing, allowed=allowed_text(ont))
        kept, drop = gate(answer, len(batch), ont)
        dropped.update(drop)
        for o in kept:
            p = batch[o["photo"] - 1]
            if ont.features[o["feature"]].span_check:
                claim = f'{ont.features[o["feature"]].claims[o["value"]]} (photo shows: "{o["quote"]}")'
                async with sem:
                    res = await PHOTO_VERIFY.ask(client, model, images=[images[o["photo"] - 1]], name=place.get("name"),
                                                 category=place.get("category") or "unknown", claim=claim)
                if res.get("verdict") != "supports":
                    dropped[f"span_check_{res.get('verdict')}"] += 1
                    continue
            pid = p["photo_id"]
            obs.append(observation(
                id=f"gmaps_photo:{pid}:{seq[pid]}", place_fid=place["fid"], feature=o["feature"], value=o["value"],
                context=dict.fromkeys(CONTEXT_KEYS, UNKNOWN), source_type="gmaps_photo", source_id=pid,
                author=f"gmaps:owner:{place['fid']}" if p["owner"] else p.get("author_hash"),
                observed_at=f"{p['month']}-01" if p.get("month") else doc["fetched_at"][:10], quote=o["quote"],
                field=p["file"], extractor=f"photo_observe@{PHOTO_OBSERVE.prompt_hash}", ontology_version=ont.version))
            seq[pid] += 1
    return {"place_fid": place["fid"], "place_name": place.get("name"), "as_of": doc["fetched_at"][:10],
            "observations": obs, "proposed": [], "ratings": [], "place": {}, "place_facts": {},
            "voices": len({p.get("author_hash") or p["photo_id"] for p in photos}),
            "stats": {"photos": len(photos), "dropped": dict(dropped)}}


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "gmaps"
    out = root / OUT_DIR
    ont = load_ontology()
    dirs = sorted(f.parent for f in (root / "places").glob(f"*/{PHOTOS_FILE}"))
    items = listed(city)
    if items is not None:
        keep = {safe_name(r["fid"]) for r in items}
        dirs = [d for d in dirs if d.name in keep]
    dirs = dirs[:limit] if limit is not None else dirs
    client, model = _client()
    sem = asyncio.Semaphore(PHOTO_OBSERVE.parallel)
    ph = hashlib.sha256((KEY + "|" + ont.prompt_text()).encode()).hexdigest()[:12]

    async def one(d: Path) -> str:
        target = out / f"{d.name}.json"
        h = hashlib.sha256((d / PHOTOS_FILE).read_bytes()).hexdigest()[:16]
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if old.get("input_hash") == h and (keep_stale()
                    or (old.get("prompt_hash"), old.get("ontology_version")) == (ph, ont.version)):
                return "cached"
        try:
            res = await observe_place(client, model, sem, name, d, ont)
        except Exception as e:
            append_jsonl(root / "photo_observe_errors.jsonl", {"at": now(), "place": d.name,
                                                               "error": f"{type(e).__name__}: {e}"[:300]})
            target.unlink(missing_ok=True)
            return "failed"
        write_json(target, {**res, "input_hash": h, "prompt_hash": ph, "ontology_version": ont.version,
                            "model": model, "built_at": now()})
        return "done"

    status = collections.Counter(await asyncio.gather(*(one(d) for d in dirs)))
    summary = {"at": now(), "places": len(dirs), "status": dict(status)}
    print(f"gmaps photo_observe {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
