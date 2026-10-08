"""Pick the gallery of every place in the web snapshot -> web/public/data/covers.json (the first photo is the cover).

A gallery photo shows the place, not the people in it. Candidates are the place's Google Maps photos
(data/gmaps/places/<fid>/photos) and the keyframes of its TikTok clips (data/tiktok/videos/<id>/frames).
1. A person detector (YOLO, COCO class 0) rejects any image where one person covers more than PERSON_MAX of the
   frame; a few small figures far away are fine.
2. Near duplicates (perceptual hash, Hamming distance <= PHASH_MAX) keep only the sharpest copy.
3. The RANK_MAX best by the heuristic (Maps photos first, then sharper, then wider) go to the Extractor in one call
   (corpus.llm.PHOTO_RANK, Gemma): beauty 1-10 and shows_place 1-10 per photo, validated here. Photos the model did
   not score keep their heuristic order after the scored ones; a failed call leaves the heuristic order.
4. score = beauty + shows_place, the heuristic breaks ties. Up to KEEP per place are written; a place with none
   gets no entry and the web draws its line art instead.
covers.json maps place id -> [photo]. When it would pass SPLIT_BYTES, each place's full list goes to
covers/<id with ':' -> '_'>.json and covers.json keeps only the cover; the web loads the rest when a place opens.
Model scores are cached in .cache/photo_rank.json by the photos sent and the prompt, so a rerun only asks for new sets.

Usage (repo root): .venv/bin/python web/scripts/pick_covers.py [--limit N] [--ids a,b] [--dry-run] [--resume]
Ops (docs/plans/SESSION_TIKTOK.md, user 2026-10-08): pause logs/tiktok_lan_uit_lane.sh while this runs, restart after.
Then: python web/scripts/make_thumbs.py for the thumbnails of the new photos.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from corpus.llm import PHOTO_RANK  # noqa: E402

SNAPSHOT = ROOT / "web/public/data/snapshot.json"
OUT = ROOT / "web/public/data/covers.json"
SPLIT_DIR = ROOT / "web/public/data/covers"
CACHE = ROOT / ".cache/photo_rank.json"
GMAPS = ROOT / "data/gmaps/places"
TIKTOK = ROOT / "data/tiktok/videos"

PERSON_MAX = 0.015  # largest person box allowed, as a share of the image area
PHASH_MAX = 8  # Hamming distance at or under which two photos are the same picture
KEEP = 12
RANK_MAX = 16  # photos sent to the model per place
RANK_PX = 640  # longest side of a photo sent to the model
MAX_VIDEOS = 6
BATCH = 32
SPLIT_BYTES = 3_000_000
FIELDS = ("src", "credit", "kind", "w", "h")


def candidates(place: dict) -> list[dict]:
    out = []
    pdir = GMAPS / place["id"].replace(":", "_")
    meta = pdir / "photos.json"
    if meta.exists():
        for ph in json.loads(meta.read_text(encoding="utf-8")).get("photos", []):
            f = pdir / ph["file"]
            if f.exists() and ph.get("kind") == "photo":
                out.append({"path": f, "src": f"/media/gmaps/{pdir.name}/{ph['file']}", "credit": "Google Maps",
                            "kind": "gmaps", "owner": bool(ph.get("owner"))})
    for v in place.get("videos", [])[:MAX_VIDEOS]:
        for i in range(1, 5):
            f = TIKTOK / v["id"] / "frames" / f"f{i}.jpg"
            if f.exists():
                out.append({"path": f, "src": f"/media/tiktok/{v['id']}/frames/f{i}.jpg",
                            "credit": f"@{v['handle']}" if v.get("handle") else "TikTok", "kind": "tiktok", "url": v.get("url")})
    return out


def sharpness(img) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def phash(img) -> int:
    """64-bit perceptual hash: signs of the 8x8 lowest frequencies of the 32x32 grey DCT against their median."""
    gray = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 32), interpolation=cv2.INTER_AREA)
    low = cv2.dct(np.float32(gray))[:8, :8].flatten()
    bits = low > np.median(low[1:])
    return int("".join("1" if b else "0" for b in bits), 2)


def distinct(photos: list[dict]) -> list[dict]:
    """Drop near duplicates, keeping the sharpest of each."""
    kept: list[dict] = []
    for p in sorted(photos, key=lambda p: -p["sharp"]):
        if all(bin(p["hash"] ^ k["hash"]).count("1") > PHASH_MAX for k in kept):
            kept.append(p)
    return kept


def screened(model, cands: list[dict], stats: dict) -> list[dict]:
    """Photos without a large person, each with its heuristic score, sharpness and hash."""
    kept = []
    for i in range(0, len(cands), BATCH):
        chunk = cands[i : i + BATCH]
        imgs = [cv2.imread(str(c["path"])) for c in chunk]
        pairs = [(c, im) for c, im in zip(chunk, imgs) if im is not None]
        if not pairs:
            continue
        results = model.predict([im for _, im in pairs], classes=[0], conf=0.35, imgsz=512, half=True, verbose=False)
        for (c, im), r in zip(pairs, results):
            stats["images"] += 1
            h, w = im.shape[:2]
            biggest = max(((b[2] - b[0]) * (b[3] - b[1]) for b in r.boxes.xyxy.tolist()), default=0.0) / (w * h)
            if biggest > PERSON_MAX:
                stats["rejected_people"] += 1
                continue
            sharp = sharpness(im)
            score = (2.0 if c["kind"] == "gmaps" else 0.0) + min(sharp / 400, 1.5) + (0.4 if w >= h else 0.0)
            kept.append({**c, "w": w, "h": h, "score": round(score, 3), "sharp": sharp, "hash": phash(im)})
    return kept


def jpeg(path: Path) -> bytes:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    if max(h, w) > RANK_PX:
        f = RANK_PX / max(h, w)
        img = cv2.resize(img, (round(w * f), round(h * f)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def scores(answer, n: int) -> dict[int, tuple[int, int]]:
    """photo number -> (beauty, shows_place) for every well-formed entry; anything else is left unscored."""
    out: dict[int, tuple[int, int]] = {}
    for e in answer.get("photos", []) if isinstance(answer, dict) else []:
        i, b, s = e.get("photo"), e.get("beauty"), e.get("shows_place")
        if all(isinstance(x, int) and not isinstance(x, bool) for x in (i, b, s)) and 1 <= i <= n and i not in out \
                and 1 <= b <= 10 and 1 <= s <= 10:
            out[i] = (b, s)
    return out


async def rank_all(places: list[tuple[dict, list[dict]]], cache: dict, stats: dict) -> None:
    """Fill p["beauty"], p["shows_place"] in place for each place's photos (cached or asked)."""
    client, model = PHOTO_RANK.role.client()
    client = client.with_options(timeout=300, max_retries=0)
    sem = asyncio.Semaphore(PHOTO_RANK.parallel)

    async def one(place: dict, photos: list[dict]) -> None:
        key = PHOTO_RANK.prompt_hash + "|" + "|".join(p["src"] for p in photos)
        got = cache.get(key)
        if got is None:
            try:
                async with sem:
                    answer = await PHOTO_RANK.ask(client, model, images=[jpeg(p["path"]) for p in photos], city="Đà Lạt",
                                                  count=len(photos), name=place["name"], category=place.get("category") or "unknown")
            except Exception as e:  # the heuristic order stands for this place
                stats["rank_failed"] += 1
                print(f"photo_rank {place['id']}: {type(e).__name__}: {str(e)[:160]}", flush=True)
                return
            got = {str(i): list(v) for i, v in scores(answer, len(photos)).items()}
            cache[key] = got
            stats["ranked"] += 1
        stats["unscored_photos"] += len(photos) - len(got)
        for i, p in enumerate(photos, 1):
            if str(i) in got:
                p["beauty"], p["shows_place"] = got[str(i)]

    await asyncio.gather(*(one(pl, ph) for pl, ph in places if len(ph) > 1))


def order(photos: list[dict]) -> list[dict]:
    """Scored photos by beauty + shows_place (heuristic breaks ties), then unscored ones by the heuristic."""
    return sorted(photos, key=lambda p: (("beauty" not in p), -(p.get("beauty", 0) + p.get("shows_place", 0)), -p["score"]))


def gallery(photos: list[dict]) -> list[dict]:
    return [{k: p[k] for k in FIELDS} | ({"url": p["url"]} if p.get("url") else {}) for p in order(photos)[:KEEP]]


def write(covers: dict[str, list[dict]]) -> str:
    full = json.dumps(covers, ensure_ascii=False, separators=(",", ":"))
    if len(full.encode()) <= SPLIT_BYTES:
        OUT.write_text(full, encoding="utf-8")
        return f"{len(full.encode()):,} bytes"
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SPLIT_DIR.glob("*.json"):
        old.unlink()
    for pid, photos in covers.items():
        (SPLIT_DIR / f"{pid.replace(':', '_')}.json").write_text(json.dumps(photos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUT.write_text(json.dumps({pid: photos[:1] for pid, photos in covers.items()}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return f"split: {len(covers)} files in {SPLIT_DIR.relative_to(ROOT)}, cover only in {OUT.name}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="comma-separated place ids (with --dry-run: print their ranking)")
    ap.add_argument("--dry-run", action="store_true", help="print the ranking, write nothing but the model cache")
    ap.add_argument("--resume", action="store_true", help="keep places already in covers.json, pick only the rest")
    ap.add_argument("--model", default=str(ROOT / ".cache/yolo11s.pt"))  # downloaded on first run
    args = ap.parse_args()
    places = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["places"]
    if args.ids:
        want = set(args.ids.split(","))
        places = [p for p in places if p["id"] in want]
    if args.limit:
        places = places[: args.limit]
    covers: dict[str, list[dict]] = {}
    if args.resume and OUT.exists():
        covers = json.loads(OUT.read_text(encoding="utf-8"))
        for pid in covers:
            f = SPLIT_DIR / f"{pid.replace(':', '_')}.json"
            if f.exists():
                covers[pid] = json.loads(f.read_text(encoding="utf-8"))
        places = [p for p in places if p["id"] not in covers]
    yolo = YOLO(args.model)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    stats = {"places": 0, "with_cover": 0, "images": 0, "rejected_people": 0, "near_duplicates": 0, "ranked": 0,
             "rank_failed": 0, "unscored_photos": 0}
    picked: list[tuple[dict, list[dict]]] = []
    for n, place in enumerate(places, 1):
        stats["places"] += 1
        ok = screened(yolo, candidates(place), stats)
        uniq = distinct(ok)
        stats["near_duplicates"] += len(ok) - len(uniq)
        picked.append((place, sorted(uniq, key=lambda p: -p["score"])[:RANK_MAX]))
        if n % 100 == 0:
            print(f"screened {n}/{len(places)} places, {stats}", flush=True)
    asyncio.run(rank_all(picked, cache, stats))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    for place, photos in picked:
        if args.dry_run:
            print(f"\n{place['name']} ({place['id']}): {len(photos)} photos sent")
            for p in order(photos):
                print(f"  {p.get('beauty', '-'):>2} + {p.get('shows_place', '-'):>2}  heur {p['score']:.2f}  {p['src']}")
        elif photos:
            stats["with_cover"] += 1
            covers[place["id"]] = gallery(photos)
    if not args.dry_run:
        print(f"wrote {OUT.relative_to(ROOT)} ({write(covers)})")
    print(stats)


if __name__ == "__main__":
    main()
