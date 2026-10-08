"""Make the light WebP thumbnails the user web shows in place of the original photos.

Every photo in web/public/data/covers.json and web/src/user/landing/places.json gets a WebP at most 480px wide:
/media/<source>/<rest>.jpg -> data/thumbs/<source>/<rest>.webp, served at /media/thumb/<source>/<rest>.webp by
web/server.mjs (and the Vite dev server). Sources stay in their own folders. Existing thumbnails are kept, so a
re-run only does new photos. Run from the repo root:

    python web/scripts/make_thumbs.py
"""

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {"gmaps": ROOT / "data" / "gmaps" / "places", "tiktok": ROOT / "data" / "tiktok" / "videos"}
OUT = ROOT / "data" / "thumbs"
WIDTH = 480  # web/src/user/ui/common.tsx THUMB_W
QUALITY = 72


def srcs() -> set[str]:
    covers = json.loads((ROOT / "web" / "public" / "data" / "covers.json").read_text(encoding="utf-8"))
    landing = json.loads((ROOT / "web" / "src" / "user" / "landing" / "places.json").read_text(encoding="utf-8"))
    out = {c["src"] for cs in covers.values() for c in cs}
    out |= {ph["src"] for p in landing for ph in p.get("photos", [])}
    return out


def paths(src: str) -> tuple[Path, Path] | None:
    parts = src.split("/", 3)  # "", "media", source, rest
    if len(parts) != 4 or parts[1] != "media" or parts[2] not in SOURCES:
        return None
    root = SOURCES[parts[2]]
    original = (root / parts[3]).resolve()
    if not original.is_relative_to(root):
        return None
    return original, (OUT / parts[2] / parts[3]).with_suffix(".webp")


def make(job: tuple[Path, Path]) -> str:
    original, thumb = job
    try:
        with Image.open(original) as im:
            im = im.convert("RGB")
            if im.width > WIDTH:
                im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
            thumb.parent.mkdir(parents=True, exist_ok=True)
            tmp = thumb.with_suffix(".tmp")
            im.save(tmp, "WEBP", quality=QUALITY, method=5)
            tmp.replace(thumb)
        return "made"
    except (OSError, ValueError):
        return "failed"


def main() -> None:
    jobs, missing = [], 0
    for src in sorted(srcs()):
        p = paths(src)
        if not p or not p[0].is_file():
            missing += 1
        elif not p[1].is_file():
            jobs.append(p)
    counts: dict[str, int] = {}
    with ProcessPoolExecutor() as pool:
        for r in pool.map(make, jobs, chunksize=16):
            counts[r] = counts.get(r, 0) + 1
    print(f"thumbs: {counts.get('made', 0)} made, {counts.get('failed', 0)} failed, {missing} originals missing -> {OUT}")


if __name__ == "__main__":
    main()
