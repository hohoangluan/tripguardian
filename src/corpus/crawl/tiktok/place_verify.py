"""Place phase 4, place_verify: does each downloaded video really show or talk about the place it was matched to?

place_filter matched videos to places from captions only. Here an Extractor-role call reads the caption, hashtags,
checked transcript (asr_check) and FRAMES evenly spaced frames (saved to videos/<video_id>/frames/) for every
(video, place) pair and returns yes / no / unsure with evidence. Writes only video.json "places": [{fid, name,
verdict, evidence[], reason, model, prompt_hash, transcript_at, checked_at}], one entry per matched place; only "yes"
makes the video evidence for that place. A pair is judged again when the transcript or the prompt changes. Waits for
asr_check: a video whose transcript is not checked yet is left for the next run. Prompt: corpus.llm.PLACE_VIDEO_VERIFY.
"""

import asyncio
import collections
import json
import subprocess
from pathlib import Path

from ...llm import PLACE_VIDEO_VERIFY
from ..common.files import data_dir, load_config, log_error, now, write_json
from .place_filter import places_by_video

FRAMES = 4
FRAME_WIDTH = 512  # enough to read signs and overlays, small enough for four images per call


def _client():
    return PLACE_VIDEO_VERIFY.role.client()


def frames(mp4: Path, total_s: float, out_dir: Path) -> list[bytes]:
    """FRAMES JPEGs at the middle of equal slices of the video; extracted once, then read from disk."""
    out = []
    for i in range(FRAMES):
        f = out_dir / f"f{i + 1}.jpg"
        if not f.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{(i + 0.5) * total_s / FRAMES:.2f}",
                            "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2", str(f)], check=True)
        out.append(f.read_bytes())
    return out


def transcript_text(t: dict) -> str:
    if t["check"]["quality"] == "no_speech":
        return "(no speech)"
    return " ".join(f"[{s['start_s']:.0f}s] {s['checked_text']}" for s in t["segments"] if s["checked_text"]) or "(no usable speech)"


def done(entry: dict | None, t: dict) -> bool:
    return bool(entry) and entry.get("prompt_hash") == PLACE_VIDEO_VERIFY.prompt_hash and entry.get("transcript_at") == t["at"]


async def run(city: str) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    by_video = places_by_video(city)
    client, model = _client()
    sem = asyncio.Semaphore(PLACE_VIDEO_VERIFY.parallel)
    verdicts = collections.Counter()
    waiting, errors = [0], [0]

    async def one(video_id: str, places: list[dict]):
        d = root / "videos" / video_id
        if not (d / "video.mp4").exists():
            return
        v = json.loads((d / "video.json").read_text(encoding="utf-8"))
        t = v.get("transcript")
        if not t or not t.get("check") or t["check"].get("transcript_at") != t["at"]:
            waiting[0] += 1  # asr / asr_check first
            return
        old = {e["fid"]: e for e in v.get("places") or []}
        entries, changed = [], False
        for p in places:
            if done(old.get(p["fid"]), t):
                entries.append(old[p["fid"]])
                continue
            async with sem:
                try:
                    images = await asyncio.to_thread(frames, d / "video.mp4", t["total_s"], d / "frames")
                    llm = await PLACE_VIDEO_VERIFY.ask(
                        client, model, images=images, city=name, frames=FRAMES, name=p["name"],
                        category=p.get("category") or "unknown", address=p.get("address") or "unknown",
                        others="; ".join(f"{o['name']} ({o.get('address') or 'address unknown'})"
                                         for o in places if o["fid"] != p["fid"]) or "none",
                        desc=v.get("caption") or "", hashtags=" ".join(f"#{h}" for h in v.get("hashtags") or []),
                        transcript=transcript_text(t))
                except Exception as e:
                    errors[0] += 1
                    log_error(root, f"{video_id}@{p['fid']}", "place_verify", e)
                    if p["fid"] in old:
                        entries.append(old[p["fid"]])
                    continue
            entries.append({"fid": p["fid"], "name": p["name"], **llm, "model": model,
                            "prompt_hash": PLACE_VIDEO_VERIFY.prompt_hash, "transcript_at": t["at"], "checked_at": now()})
            changed = True
        for e in entries:
            verdicts[e["verdict"]] += 1
        if changed:
            v = json.loads((d / "video.json").read_text(encoding="utf-8"))  # read late: keep other phases' writes
            v["places"] = entries
            write_json(d / "video.json", v)

    await asyncio.gather(*(one(vid, ps) for vid, ps in by_video.items()))
    summary = {"at": now(), "videos": len(by_video), "verdicts": dict(verdicts), "waiting_for_asr": waiting[0],
               "llm_errors": errors[0]}
    print(f"place_verify {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
