"""gmaps style_observe: a place's Maps photos -> style tags (config/styles.yaml) in
data/gmaps/style_observations/<fid_dir>.json, for corpus.index (layer B). Soft taste only: never a hard filter, never
"absent". Only places of the serving file are read. A place is done again when its photos.json, the prompt or the
style vocabulary change; a failed place has no file this run and a line in data/gmaps/style_observe_errors.jsonl.
Same vote rule as photo_observe: one poster = one author, the business's own photos one author per place."""

import asyncio
import collections
import hashlib
import json
from pathlib import Path

import yaml

from ...crawl.common.files import ROOT, append_jsonl, data_dir, load_config, now, safe_name, write_json
from ...llm import STYLE_OBSERVE
from ...ontology import UNKNOWN
from .. import CONTEXT_KEYS, observation
from .photos import BATCH, PHOTOS_FILE, _client

OUT_DIR = "style_observations"
STYLES_FILE = ROOT / "config" / "styles.yaml"


def vocabulary() -> dict:
    return yaml.safe_load(STYLES_FILE.read_text(encoding="utf-8"))


def allowed_text(voc: dict) -> str:
    return "\n".join(f"- {s['id']}{' (a kind of ' + s['parent'] + ')' if s.get('parent') else ''}: {s['hint']}"
                     for s in voc["styles"])


def gate(answer: dict, n: int, ids: set[str]) -> tuple[list[dict], collections.Counter]:
    if not isinstance(answer, dict) or not isinstance(answer.get("observations"), list):
        raise ValueError("answer has no observations list")
    kept, dropped, seen = [], collections.Counter(), set()
    for o in answer["observations"]:
        f, v, i, q = o.get("feature"), o.get("value"), o.get("photo"), (o.get("quote") or "").strip()
        if f not in ids or v != "present":
            dropped["not_allowed"] += 1
        elif not isinstance(i, int) or not 1 <= i <= n:
            dropped["bad_photo"] += 1
        elif not q:
            dropped["no_quote"] += 1
        elif (f, i) in seen:
            dropped["duplicate"] += 1
        else:
            seen.add((f, i))
            kept.append({"feature": f, "value": "present", "photo": i, "quote": q})
    return kept, +dropped


async def observe_place(client, model: str, sem: asyncio.Semaphore, city: str, d: Path, voc: dict) -> dict:
    place = json.loads((d / "place.json").read_text(encoding="utf-8"))
    doc = json.loads((d / PHOTOS_FILE).read_text(encoding="utf-8"))
    photos = [p for p in doc["photos"] if not p.get("stale") and (d / p["file"]).exists()]  # stale = cover only
    ids = {s["id"] for s in voc["styles"]}
    obs, dropped = [], collections.Counter()
    for start in range(0, len(photos), BATCH):
        batch = photos[start:start + BATCH]
        images = [(d / p["file"]).read_bytes() for p in batch]
        listing = "; ".join(f"{i} = {'owner' if p['owner'] else 'visitor'} {p['kind']}" for i, p in enumerate(batch, 1))
        async with sem:
            answer = await STYLE_OBSERVE.ask(client, model, images=images, city=city, count=len(batch),
                                             name=place.get("name"), category=place.get("category") or "unknown",
                                             photo_list=listing, allowed=allowed_text(voc))
        kept, drop = gate(answer, len(batch), ids)
        dropped.update(drop)
        for o in kept:
            p = batch[o["photo"] - 1]
            obs.append(observation(
                id=f"gmaps_style:{p['photo_id']}:{o['feature']}", place_fid=place["fid"], feature=o["feature"],
                value="present", context=dict.fromkeys(CONTEXT_KEYS, UNKNOWN), source_type="gmaps_photo",
                source_id=p["photo_id"], author=f"gmaps:owner:{place['fid']}" if p["owner"] else p.get("author_hash"),
                observed_at=f"{p['month']}-01" if p.get("month") else doc["fetched_at"][:10], quote=o["quote"],
                field=p["file"], extractor=f"style_observe@{STYLE_OBSERVE.prompt_hash}", ontology_version=voc["version"]))
    return {"place_fid": place["fid"], "place_name": place.get("name"), "as_of": doc["fetched_at"][:10],
            "observations": obs, "stats": {"photos": len(photos), "dropped": dict(dropped)}}


async def run(city: str, limit: int | None = None, shard: tuple[int, int] | None = None) -> dict:
    """shard (i, n): only every n-th place from i, so a LAN and a UIT process (EXTRACTOR_ON_UIT=1) split the work."""
    name, _ = load_config(city)
    root = data_dir() / "gmaps"
    out = root / OUT_DIR
    voc = vocabulary()
    serving = json.loads((data_dir() / "serving" / "places.json").read_text(encoding="utf-8"))["records"]
    dirs = [root / "places" / safe_name(r["id"]) for r in serving]
    dirs = [d for d in dirs if (d / PHOTOS_FILE).exists()]
    dirs = dirs[shard[0]::shard[1]] if shard else dirs
    dirs = dirs[:limit] if limit is not None else dirs
    client, model = _client()
    sem = asyncio.Semaphore(STYLE_OBSERVE.role.parallel())
    ph = hashlib.sha256((STYLE_OBSERVE.prompt_hash + str(BATCH) + allowed_text(voc)).encode()).hexdigest()[:12]

    async def one(d: Path) -> str:
        target = out / f"{d.name}.json"
        h = hashlib.sha256((d / PHOTOS_FILE).read_bytes()).hexdigest()[:16]
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("input_hash"), old.get("prompt_hash")) == (h, ph):
                return "cached"
        try:
            res = await observe_place(client, model, sem, name, d, voc)
        except Exception as e:
            append_jsonl(root / "style_observe_errors.jsonl", {"at": now(), "place": d.name,
                                                               "error": f"{type(e).__name__}: {e}"[:300]})
            target.unlink(missing_ok=True)
            return "failed"
        write_json(target, {**res, "input_hash": h, "prompt_hash": ph, "styles_version": voc["version"],
                            "model": model, "built_at": now()})
        return "done"

    status = collections.Counter(await asyncio.gather(*(one(d) for d in dirs)))
    summary = {"at": now(), "places": len(dirs), "status": dict(status)}
    print(f"gmaps style_observe {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
