"""Pack the data a fresh clone needs to run the whole stack (./run.sh start) into one zip for sharing.

Packs data/ with paths relative to the repo root, so unpacking at the repo root restores it in place
(web/public/data/snapshot.json is in git). Leaves out what no running service reads:
  - data/tiktok/videos/*/video.mp4: only the ASR crawl steps read the clip; transcripts and frames are kept
  - logs, pid files, half-written *.tmp, shell scripts dropped into data/
  - data/gmaps/observations_before_v6: backup taken before the v6 observe rerun
--no-photos also leaves out the Maps photos (data/gmaps/places/*/photos, ~2.4 GB); only /admin/labels shows them.

Usage (from the repo root):
    python scripts/pack_data.py [--no-photos] [--out DIR]    -> DIR/tripguardian-data-<YYYYMMDD>.zip (DIR: repo root)
Unpack in a fresh clone:
    python -m zipfile -e tripguardian-data-<YYYYMMDD>.zip .
"""
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_NAMES = {"video.mp4"}
SKIP_SUFFIXES = {".tmp", ".log", ".err", ".pid", ".sh"}
SKIP_DIRS = {("data", "gmaps", "observations_before_v6")}
STORED = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}  # already compressed


def keep(rel: Path, photos: bool) -> bool:
    if rel.name in SKIP_NAMES or rel.suffix in SKIP_SUFFIXES:
        return False
    if any(rel.parts[:len(d)] == d for d in SKIP_DIRS):
        return False
    if not photos and rel.parts[:3] == ("data", "gmaps", "places") and "photos" in rel.parts[3:-1]:
        return False
    return True


def main(photos: bool, out_dir: Path) -> None:
    files = [p for p in sorted((ROOT / "data").rglob("*")) if p.is_file() and keep(p.relative_to(ROOT), photos)]
    out = out_dir / f"tripguardian-data-{date.today():%Y%m%d}.zip"
    with zipfile.ZipFile(out, "w", allowZip64=True) as z:
        for i, p in enumerate(files, 1):
            kind = zipfile.ZIP_STORED if p.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
            z.write(p, p.relative_to(ROOT).as_posix(), compress_type=kind)
            if i % 5000 == 0:
                print(f"{i}/{len(files)} files")
    print(f"{len(files)} files -> {out.name} ({out.stat().st_size / 1048576:.0f} MB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    main("--no-photos" not in args, Path(args[args.index("--out") + 1]) if "--out" in args else ROOT)
