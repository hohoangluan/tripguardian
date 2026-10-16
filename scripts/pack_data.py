"""Pack the data a fresh clone needs to run the whole stack (./run.sh start) into one zip for sharing.

Packs data/ plus the files kept out of the public repo because they quote real people (reviews, TikTok handles and
comments): web/public/data/{snapshot,covers}.json and the captured test pages in tests/fixtures/{gmaps,tiktok}. Paths are
relative to the repo root, so unpacking at the repo root restores them in place. Leaves out what no service reads:
  - data/tiktok/videos/*/video.mp4: only the ASR crawl steps read the clip; transcripts and frames are kept
  - logs, pid files, half-written *.tmp, shell scripts dropped into data/
  - data/gmaps/observations_before_v6: backup taken before the v6 observe rerun
--no-photos also leaves out the Maps photos (data/gmaps/places/*/photos, ~2.4 GB): /admin/labels and the web's place
covers show them; without them covers fall back to clip frames, then to line art.

Usage (from the repo root):
    python scripts/pack_data.py [--no-photos] [--out DIR]    -> DIR/tripguardian-data-<YYYYMMDD>.zip (DIR: repo root)
Unpack in a fresh clone:
    python -m zipfile -e tripguardian-data-<YYYYMMDD>.zip .
"""
import sys
import json
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRA = ("web/public/data/snapshot.json", "web/public/data/snapshot-admin.json", "web/public/data/covers.json", "tests/fixtures/gmaps", "tests/fixtures/tiktok")
SKIP_NAMES = {"video.mp4"}
SKIP_SUFFIXES = {".tmp", ".log", ".err", ".pid", ".sh"}
SKIP_DIRS = {("data", "gmaps", "observations_before_v6")}
STORED = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}  # already compressed
CORPUS_DIRS = {"gmaps", "tiktok", "official", "reports", "review", "intel", "serving", "snapshot", "index", "thumbs", "releases"}


def keep(rel: Path, photos: bool, active_release: str | None = None) -> bool:
    if rel.name in SKIP_NAMES or rel.suffix in SKIP_SUFFIXES:
        return False
    if any(rel.parts[:len(d)] == d for d in SKIP_DIRS):
        return False
    if rel.parts[0] == "data":
        if len(rel.parts) < 2 or rel.parts[1] not in CORPUS_DIRS:
            return False
        if any("backup" in part or "before_" in part or part.startswith(".staging-") for part in rel.parts[:-1]):
            return False
        if rel.parts[1] == "releases" and len(rel.parts) > 2 and rel.parts[2] != "current" and rel.parts[2] != active_release:
            return False
    if not photos and rel.parts[:3] == ("data", "gmaps", "places") and "photos" in rel.parts[3:-1]:
        return False
    return True


def main(photos: bool, out_dir: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from corpus.releases import resolve, validate
    data = ROOT / "data"
    release = resolve(data)
    active = release.name if release != data else None
    manifest = validate(release) if active else None
    allowed = {i["path"] for i in manifest["artifacts"]} | {"manifest.json"} if manifest else set()
    files = []
    import os
    for current, dirs, names in os.walk(data):
        base = Path(current)
        dirs[:] = [d for d in dirs if "backup" not in d and "before_" not in d and not d.startswith(".staging-")]
        if base == data:
            dirs[:] = [d for d in dirs if d in CORPUS_DIRS and (not active or d not in ("intel", "serving", "snapshot", "index"))]
        elif base == data / "releases":
            dirs[:] = [d for d in dirs if d == active]
        if not photos and base.parent.parent == data / "gmaps" / "places":
            dirs[:] = [d for d in dirs if d != "photos"]
        for name in names:
            p = base / name
            rel = p.relative_to(ROOT)
            if not keep(rel, photos, active):
                continue
            if active and rel.parts[1] in ("intel", "serving", "snapshot", "index"):
                continue
            if active and rel.parts[1] == "releases" and rel.parts[2] != "current":
                if p.relative_to(release).as_posix() not in allowed:
                    continue
            files.append(p)
    files.sort()
    for e in map(ROOT.joinpath, EXTRA):
        if not e.exists():
            print(f"warning: {e.relative_to(ROOT)} missing, not packed")
        files += [e] if e.is_file() else sorted(p for p in e.rglob("*") if p.is_file())
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
