"""Pick cover images for every place in the web snapshot -> web/public/data/covers.json.

A cover shows the place, not the people in it. Candidates are the place's Google Maps photos
(data/gmaps/places/<fid>/photos) and the keyframes of its TikTok clips (data/tiktok/videos/<id>/frames).
A person detector (YOLO, COCO class 0) rejects any image where one person covers more than PERSON_MAX of the
frame; a few small figures far away are fine. The rest are ranked: Maps photos first (taken of the place itself),
then sharper, then wider. Up to KEEP per place are written; a place with none gets no entry and the web draws
its line art instead.

Usage (repo root): python web/scripts/pick_covers.py [--limit N] [--resume] [--model path/to/yolo.pt]
Run again after new photos or clips: it rereads everything (about a minute per thousand images on a GPU).
"""

import argparse
import json
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "web/public/data/snapshot.json"
OUT = ROOT / "web/public/data/covers.json"
GMAPS = ROOT / "data/gmaps/places"
TIKTOK = ROOT / "data/tiktok/videos"

PERSON_MAX = 0.015  # largest person box allowed, as a share of the image area
KEEP = 4
MAX_VIDEOS = 6
BATCH = 32


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true", help="keep places already in covers.json, pick only the rest")
    ap.add_argument("--model", default=str(ROOT / ".cache/yolo11s.pt"))  # downloaded on first run
    args = ap.parse_args()
    places = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["places"]
    if args.limit:
        places = places[: args.limit]
    model = YOLO(args.model)
    covers: dict[str, list[dict]] = json.loads(OUT.read_text(encoding="utf-8")) if args.resume and OUT.exists() else {}
    done = set(covers) if args.resume else set()
    stats = {"places": 0, "with_cover": 0, "images": 0, "rejected_people": 0}
    for n, place in enumerate(places, 1):
        if place["id"] in done:
            continue
        cands = candidates(place)
        stats["places"] += 1
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
                score = (2.0 if c["kind"] == "gmaps" else 0.0) + min(sharpness(im) / 400, 1.5) + (0.4 if w >= h else 0.0)
                kept.append({**c, "w": w, "h": h, "score": round(score, 3)})
        kept.sort(key=lambda c: -c["score"])
        if kept:
            stats["with_cover"] += 1
            covers[place["id"]] = [{k: c[k] for k in ("src", "credit", "kind", "w", "h") if k in c} | ({"url": c["url"]} if c.get("url") else {})
                                   for c in kept[:KEEP]]
        if n % 100 == 0:
            OUT.write_text(json.dumps(covers, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"{n}/{len(places)} places, {stats}", flush=True)
    OUT.write_text(json.dumps(covers, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {stats}")


if __name__ == "__main__":
    main()
