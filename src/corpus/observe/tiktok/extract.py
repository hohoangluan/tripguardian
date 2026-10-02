"""tiktok observe: every (video, place) pair place_verify accepted -> data/tiktok/observations/<fid_dir>.json.

Per pair one Extractor call (corpus.llm.VIDEO_OBSERVE) reads the caption, the checked transcript segments (ok /
fixed only, numbered, with times) and, when the video is about this place alone, its keyframes. The gate keeps an
observation only when the feature and value are in the ontology, a speech quote is in the segment it names, a
caption quote is in the caption or hashtags, and a frame observation is one a picture can prove (FRAME_VALUES).
Features with `check: span` are read again (VIDEO_VERIFY: the segments around the quote, or the frame); only
"supports" is kept. One vote per creator: author = the video's author id. observed_at = the video's upload date.
A place is done again when its pairs, their transcripts, the prompts or the ontology change; a pair that fails
leaves the place without a file this run (retried next run) and a line in data/tiktok/observe_errors.jsonl.
"""

import asyncio
import collections
import hashlib
import json
import re
import unicodedata

import openai
from datetime import datetime, timezone
from pathlib import Path

from ...crawl.common.files import append_jsonl, data_dir, load_config, now, safe_name, write_json
from ...crawl.tiktok.frames import FRAMES, frames
from ...crawl.tiktok.place_verify import evidence_pairs
from ...llm import VIDEO_OBSERVE, VIDEO_VERIFY
from ...ontology import UNKNOWN, Ontology, load as load_ontology
from .. import CONTEXT_KEYS, observation

USABLE = ("ok", "fixed")  # asr_check statuses whose checked_text is speech
FRAME_VALUES = {  # what a still picture can prove; never "absent", suitability or quality. Promo videos film empty
    # rooms and wide lenses, so a frame says nothing about a quiet place or its size.
    "steep_or_stairs": {"present"}, "setting": {"indoor", "outdoor", "both"}, "crowd": {"high"},
    "scenic_view": {"present"}, "flower_garden": {"present"}, "nature": {"present"}, "outdoor_seating": {"present"},
    "cozy_decor": {"present"}, "camping": {"present"}, "rough_road_access": {"present"},
}
SOURCE_TYPE = {"speech": "tiktok_segment", "caption": "tiktok_caption", "frame": "tiktok_frame"}
CONTEXT_WINDOW = 1  # segments each side of the quoted one shown to VIDEO_VERIFY
PROMPTS_KEY = "|".join((VIDEO_OBSERVE.prompt_hash, VIDEO_VERIFY.prompt_hash, str(CONTEXT_WINDOW),
                        json.dumps({k: sorted(v) for k, v in FRAME_VALUES.items()}, sort_keys=True)))


BUSY_WAIT_S, BUSY_TRIES = 20, 45  # the Gemma key is shared with gmaps observe: on HTTP 429 wait, do not fail


async def ask(task, *args, **kwargs) -> dict:
    """task.ask, waiting out a busy shared key (Task.ask itself gives up after a few seconds)."""
    for tries in range(1, BUSY_TRIES + 1):
        try:
            return await task.ask(*args, **kwargs)
        except openai.RateLimitError:
            if tries == BUSY_TRIES:
                raise
            await asyncio.sleep(BUSY_WAIT_S)


class BadAnswer(Exception):
    pass


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip().casefold()


def segments(t: dict) -> list[dict]:
    return [{"i": i, **s} for i, s in enumerate(t.get("segments") or [], 1)
            if s.get("status") in USABLE and (s.get("checked_text") or "").strip()]


def segments_text(segs: list[dict]) -> str:
    return "\n".join(f"[{s['i']}] ({s['start_s']:.0f}-{s['end_s']:.0f}s) {s['checked_text']}" for s in segs) or "(none)"


def gate(answer: dict, segs: list[dict], caption: str, with_frames: bool, ont: Ontology):
    if not isinstance(answer, dict) or not isinstance(answer.get("observations"), list):
        raise BadAnswer("answer has no observations list")
    by_i = {s["i"]: s for s in segs}
    kept, dropped = [], collections.Counter()
    for o in answer["observations"]:
        f, v, src, ref, quote = o.get("feature"), o.get("value"), o.get("source"), o.get("ref"), (o.get("quote") or "").strip()
        if not ont.valid(f, v):
            dropped["not_in_ontology"] += 1
        elif not quote:
            dropped["no_quote"] += 1
        elif any(not ont.valid_context(k, o.get(k, UNKNOWN)) for k in CONTEXT_KEYS):
            dropped["bad_context"] += 1
        elif src == "speech" and (ref not in by_i or norm(quote) not in norm(by_i[ref]["checked_text"])):
            dropped["quote_not_in_segment"] += 1
        elif src == "caption" and norm(quote) not in norm(caption):
            dropped["quote_not_in_caption"] += 1
        elif src == "frame" and not (with_frames and 1 <= (ref or 0) <= FRAMES and v in FRAME_VALUES.get(f, ())):
            dropped["frame_not_allowed"] += 1
        elif src not in SOURCE_TYPE:
            dropped["bad_source"] += 1
        else:
            kept.append({**o, "quote": quote})
    return kept, dropped


def passage(o: dict, segs: list[dict], caption: str) -> str:
    if o["source"] == "caption":
        return f"Caption: {caption}"
    if o["source"] == "frame":
        return f"The attached frame {o['ref']} of the video."
    idx = next(n for n, s in enumerate(segs) if s["i"] == o["ref"])
    near = segs[max(0, idx - CONTEXT_WINDOW): idx + CONTEXT_WINDOW + 1]
    return "Speech (machine-transcribed): " + " ".join(s["checked_text"] for s in near)


def upload_date(v: dict) -> str | None:
    try:
        return datetime.fromtimestamp(int(v["created_at"]), timezone.utc).date().isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def places_index(city: str) -> dict[str, dict]:
    listed = data_dir() / "gmaps" / "list" / f"{city}.json"
    items = json.loads(listed.read_text(encoding="utf-8"))["items"] if listed.exists() else []
    return {r["fid"]: r for r in items}


async def observe_pair(client, model: str, sem: asyncio.Semaphore, city: str, v: dict, d: Path, place: dict,
                       others: list[str], ont: Ontology):
    t = v["transcript"]
    segs = segments(t)
    caption = " ".join([v.get("caption") or "", *(f"#{h}" for h in v.get("hashtags") or [])])
    with_frames = not others and (d / "video.mp4").exists()
    images = await asyncio.to_thread(frames, d / "video.mp4", t["total_s"], d / "frames") if with_frames else []
    async with sem:
        answer = await ask(VIDEO_OBSERVE, 
            client, model, images=images, city=city, name=place["name"], category=place.get("category") or "unknown",
            others="; ".join(others) or "none", ontology=ont.prompt_text(), frames=FRAMES,
            frame_note="attached, evenly spaced" if images else "no frames attached: do not use frame",
            frame_features=", ".join(f"{f} {'/'.join(sorted(vs))}" for f, vs in FRAME_VALUES.items()),
            desc=v.get("caption") or "", hashtags=" ".join(f"#{h}" for h in v.get("hashtags") or []),
            screen_text="; ".join(t.get("check", {}).get("screen_text") or []) or "none", segments=segments_text(segs))
    kept, dropped = gate(answer, segs, caption, bool(images), ont)
    final = []
    for o in kept:
        if ont.features[o["feature"]].span_check:
            claim = f'{ont.features[o["feature"]].claims[o["value"]]} ({o["source"]}: "{o["quote"]}")'
            async with sem:
                res = await ask(VIDEO_VERIFY, client, model, images=[images[o["ref"] - 1]] if o["source"] == "frame" else (),
                                             name=place["name"], category=place.get("category") or "unknown",
                                             claim=claim, passage=passage(o, segs, caption))
            if res.get("verdict") != "supports":
                dropped[f"span_check_{res.get('verdict')}"] += 1
                continue
        final.append(o)
    by_i = {s["i"]: s for s in segs}
    out = []
    for n, o in enumerate(final):
        seg = by_i.get(o["ref"]) if o["source"] == "speech" else None
        at = (o["ref"] - 0.5) * t["total_s"] / FRAMES if o["source"] == "frame" else None
        out.append(observation(
            id=f"tiktok:{v['video_id']}:{n}", place_fid=place["fid"], feature=o["feature"], value=o["value"],
            context={k: o.get(k, UNKNOWN) for k in CONTEXT_KEYS}, source_type=SOURCE_TYPE[o["source"]],
            source_id=v["video_id"], author=f"tiktok:{v.get('author_id')}", observed_at=upload_date(v), quote=o["quote"],
            field=o["source"], extractor=f"video_observe@{VIDEO_OBSERVE.prompt_hash}", ontology_version=ont.version,
            start_s=seg["start_s"] if seg else at, end_s=seg["end_s"] if seg else at))
    return out, dropped


def _client():
    client, model = VIDEO_OBSERVE.role.client()
    return client.with_options(timeout=240, max_retries=0), model


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    out = root / "observations"
    ont = load_ontology()
    places = places_index(city)
    by_place, by_video = collections.defaultdict(list), collections.defaultdict(list)
    for video_id, fid in sorted(evidence_pairs()):
        if fid in places:
            by_place[fid].append(video_id)
            by_video[video_id].append(fid)
    fids = sorted(by_place)[:limit] if limit is not None else sorted(by_place)
    client, model = _client()
    sem = asyncio.Semaphore(VIDEO_OBSERVE.parallel)
    key = (PROMPTS_KEY + "|" + ont.prompt_text(), ont.version)

    def video(video_id: str) -> dict:
        return json.loads((root / "videos" / video_id / "video.json").read_text(encoding="utf-8"))

    async def one(fid: str) -> str:
        target = out / f"{safe_name(fid)}.json"
        vids = {vid: video(vid) for vid in by_place[fid]}
        vids = {vid: v for vid, v in vids.items() if (v.get("transcript") or {}).get("check")}
        if not vids:
            return "waiting"
        h = hashlib.sha256(json.dumps(sorted((vid, v["transcript"]["check"].get("at")) for vid, v in vids.items()))
                           .encode()).hexdigest()[:16]
        ph = hashlib.sha256(key[0].encode()).hexdigest()[:12]
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("input_hash"), old.get("prompt_hash"), old.get("ontology_version")) == (h, ph, key[1]):
                return "cached"
        obs, dropped = [], collections.Counter()
        try:
            for vid, v in vids.items():
                others = [places[f]["name"] for f in by_video[vid] if f != fid]
                got, drop = await observe_pair(client, model, sem, name, v, root / "videos" / vid, places[fid], others, ont)
                obs += got
                dropped.update(drop)
        except Exception as e:
            append_jsonl(root / "observe_errors.jsonl", {"at": now(), "place": fid, "error": f"{type(e).__name__}: {e}"[:300]})
            return "failed"
        dates = [upload_date(v) for v in vids.values() if upload_date(v)]
        write_json(target, {"place_fid": fid, "place_name": places[fid].get("name"),
                            "as_of": max(v.get("fetched_at", "")[:10] for v in vids.values()) or now()[:10],
                            "observations": obs, "proposed": [], "ratings": [], "place": {}, "place_facts": {},
                            "voices": len({v.get("author_id") for v in vids.values()}),
                            "videos": sorted(vids), "newest_video": max(dates) if dates else None,
                            "stats": {"videos": len(vids), "dropped": dict(dropped)},
                            "input_hash": h, "prompt_hash": ph, "ontology_version": key[1], "model": model,
                            "built_at": now()})
        return "done"

    status = collections.Counter(await asyncio.gather(*(one(f) for f in fids)))
    summary = {"at": now(), "places": len(fids), "pairs": sum(len(by_place[f]) for f in fids), "status": dict(status)}
    print(f"tiktok observe {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
