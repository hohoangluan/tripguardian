"""Video phase asr_check: an Extractor-role read of every transcript: keep, fix misheard words, or drop nonsense.

ASR turns background songs and noise into nonsense and mishears names and loanwords. The model sees the segments, the
caption, hashtags and FRAMES keyframes (names on signs), and returns per segment ok / fixed / garbled / lyrics plus the
text it reads on screen. Code then guards every edit (guard): a replaced span must sound like the ASR words (accents
dropped), or sound somewhat alike and be written in the caption / hashtags / screen text, or come from ASR2; inserted
words must come from ASR2; negations are never deleted. Rejected edits are undone, and a "fixed" that keeps under
MIN_KEPT of the ASR words is a rewrite and counts as garbled. Segments that end garbled or had edits undone get
needs_alt: asr_alt transcribes them with a second ASR model ("alt_text", shown to the model as ASR2 on the next run).

Writes only video.json: transcript.segments[].{checked_text, status, needs_alt, rejected_edits}, transcript.text
(usable checked segments joined), transcript.check = {model, prompt_hash, quality, screen_text, transcript_at,
alt_hash, at}. A video with no speech gets quality "no_speech" without a model call. Checked again when the
transcript, the second-ASR texts or the prompt change. Prompt: corpus.llm.ASR_CHECK.
"""

import asyncio
import collections
import difflib
import hashlib
import json
import zlib
import re
import unicodedata

from ...llm import ASR_CHECK
from ..common.files import data_dir, load_config, log_error, now, write_json
from .frames import FRAMES, frames
from .place_filter import places_by_video

USABLE = ("ok", "fixed")
MIN_KEPT = 0.5  # a "fixed" segment must keep at least this share of the ASR words; below that it is a rewrite
SOUND_ALIKE = 0.5  # replaced span vs ASR span, accents and spaces dropped: "mini" -> "Pini" 0.75, -> "Quỷ Núi" 0.20
SOUND_NEAR = 0.3  # enough when the new words are written in the context: "ca giắt" -> "kayak" 0.36
NEGATIONS = {"khong", "chua", "chang", "cha", "dung", "ko", "k", "hong", "hok"}


def _client():
    return ASR_CHECK.role.client()


def flat(s: str) -> str:
    """Lowercase, no accents, letters and digits only: how close two spellings sound, roughly."""
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def sounds(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, flat(a), flat(b)).ratio()


def kept_share(raw: str, fixed: str) -> float:
    """How much of the raw ASR text a fix keeps (word-level match ratio, case-insensitive)."""
    return difflib.SequenceMatcher(None, raw.lower().split(), fixed.lower().split()).ratio()


def guard(raw: str, fixed: str, context: str, alt: str = "") -> tuple[str, int]:
    """The model's fix with every unsupported edit undone, and how many were undone. context and alt are flat()."""
    old, new = raw.split(), fixed.split()
    out, undone = [], 0
    ops = difflib.SequenceMatcher(None, [flat(w) for w in old], [flat(w) for w in new], autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        was, now_ = " ".join(old[i1:i2]), " ".join(new[j1:j2])
        if op == "equal":
            ok = True  # same sound; keeps the fix's casing ("đà lạt" -> "Đà Lạt")
        elif op == "replace":
            s = sounds(was, now_)
            ok = (s >= SOUND_ALIKE or (s >= SOUND_NEAR and flat(now_) in context)
                  or (bool(alt) and flat(now_) in alt))
        elif op == "insert":
            ok = bool(alt) and flat(now_) in alt  # only words the second ASR heard
        else:  # delete
            ok = not any(flat(w) in NEGATIONS for w in old[i1:i2])
        if ok:
            out += new[j1:j2]
        else:
            out += old[i1:i2]
            undone += 1
    return " ".join(out), undone


def segment_lines(segments: list[dict]) -> str:
    lines = []
    for i, s in enumerate(segments):
        line = f"{i}. [{s['start_s']:.1f}-{s['end_s']:.1f}s] ASR: {s['text']}"
        if s.get("alt_text"):
            line += f" | ASR2: {s['alt_text']}"
        lines.append(line)
    return "\n".join(lines)


def alt_hash(segments: list[dict]) -> str:
    return hashlib.sha256("\n".join(s.get("alt_text") or "" for s in segments).encode()).hexdigest()[:12]


def apply(transcript: dict, answer: dict, model: str, context: str = "") -> dict:
    """The checked transcript; raises when the answer does not cover every segment exactly once, in order."""
    segs = transcript["segments"]
    got = answer["segments"]
    if [a["i"] for a in got] != list(range(len(segs))):
        raise ValueError(f"asr_check answered segments {[a['i'] for a in got]} for {len(segs)} segments")
    ctx = context + flat(" ".join(answer.get("screen_text") or []))
    out = []
    for s, a in zip(segs, got):
        status, text, undone = a["status"], a["text"].strip(), 0
        if status in USABLE and not text:
            raise ValueError(f"segment {a['i']}: status {status} with empty text")
        alt = flat(s.get("alt_text") or "")
        if status == "fixed" and kept_share(s["text"], text) < MIN_KEPT and not alt:
            status, text = "garbled", ""  # the model rewrote it: invented text is worse than none
        if status == "fixed":
            text, undone = guard(s["text"], text, ctx, alt)
            if text == s["text"]:
                status = "ok"
        if status not in USABLE:
            text = ""
        seg = {k: v for k, v in s.items() if k not in ("checked_text", "status", "needs_alt", "rejected_edits")}
        seg.update({"checked_text": text, "status": status, "rejected_edits": undone,
                    "needs_alt": not s.get("alt_text") and (status == "garbled" or undone > 0)})
        out.append(seg)
    return {**transcript, "segments": out, "text": " ".join(s["checked_text"] for s in out if s["checked_text"]),
            "check": {"model": model, "prompt_hash": ASR_CHECK.prompt_hash, "quality": answer["quality"],
                      "screen_text": answer.get("screen_text") or [], "transcript_at": transcript["at"],
                      "alt_hash": alt_hash(segs), "at": now()}}


def needs_check(t: dict | None) -> bool:
    if not t:
        return False  # asr has not run yet
    c = t.get("check") or {}
    return (c.get("prompt_hash") != ASR_CHECK.prompt_hash or c.get("transcript_at") != t["at"]
            or c.get("alt_hash", alt_hash(t["segments"])) != alt_hash(t["segments"]))


async def run(city: str, shard: tuple[int, int] | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    docs = [d for d in sorted((root / "videos").glob("*/video.json")) if (root / "videos").exists()
            and (not shard or zlib.crc32(d.parent.name.encode()) % shard[1] == shard[0])  # stable key: shards never overlap
            and needs_check(json.loads(d.read_text(encoding="utf-8")).get("transcript"))]
    places = places_by_video(city)
    client, model = _client()
    sem = asyncio.Semaphore(ASR_CHECK.parallel)
    quality = collections.Counter()
    errors = [0]

    async def one(doc):
        v = json.loads(doc.read_text(encoding="utf-8"))
        t = v["transcript"]
        if not t["segments"]:
            checked = {**t, "text": "", "check": {"model": None, "prompt_hash": ASR_CHECK.prompt_hash,
                                                  "quality": "no_speech", "screen_text": [], "transcript_at": t["at"],
                                                  "alt_hash": alt_hash([]), "at": now()}}
        else:
            hashtags = " ".join(f"#{h}" for h in v.get("hashtags") or [])
            async with sem:
                try:
                    images = await asyncio.to_thread(frames, doc.parent / "video.mp4", t["total_s"], doc.parent / "frames")
                    answer = await ASR_CHECK.ask(
                        client, model, images=images, city=name, frames=FRAMES, desc=v.get("caption") or "",
                        hashtags=hashtags,
                        places=", ".join(p["name"] for p in places.get(v["video_id"], [])) or "unknown",
                        segments=segment_lines(t["segments"]))
                    checked = apply(t, answer, model, context=flat((v.get("caption") or "") + " " + hashtags))
                except Exception as e:
                    errors[0] += 1
                    log_error(root, v["video_id"], "asr_check", e)
                    return
        v = json.loads(doc.read_text(encoding="utf-8"))  # read late: keep what other phases wrote meanwhile
        cur = v.get("transcript") or {}
        if cur.get("at") != t["at"] or alt_hash(cur.get("segments", [])) != alt_hash(t["segments"]):
            return  # transcribed again meanwhile; checked next run
        v["transcript"] = checked
        write_json(doc, v)
        quality[checked["check"]["quality"]] += 1

    await asyncio.gather(*(one(d) for d in docs))
    summary = {"at": now(), "videos": len(docs), "quality": dict(quality), "llm_errors": errors[0]}
    print(f"asr_check {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
