"""Make the light MP4s the user web plays in place of the original TikTok clips.

Every data/tiktok/videos/<id>/video.mp4 gets a copy at most 960px tall (540x960 for a vertical clip), H.264 with the
index first (faststart) so it starts playing after the first bytes: data/thumbs/tiktok/<id>/video.mp4. web/server.mjs
sends it for /media/tiktok/<id>/video.mp4 when it exists; the original stays the source. Existing copies are kept, so
a re-run only does new clips. Encodes on the GPU (h264_nvenc) and falls back to libx264. Run from the repo root:

    python web/scripts/make_clips.py [--workers 3]   # a GeForce card runs at most 3 NVENC sessions
"""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "tiktok" / "videos"
OUT = ROOT / "data" / "thumbs" / "tiktok"
HEIGHT = 960
SCALE = f"scale=-2:'min({HEIGHT},ih)'"
AUDIO = ["-c:a", "aac", "-b:a", "96k", "-ac", "2"]
ENCODERS = (
    ["-c:v", "h264_nvenc", "-preset", "slow", "-rc", "vbr_hq", "-cq", "28", "-b:v", "0", "-maxrate", "1200k", "-bufsize", "2400k"],
    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-maxrate", "1200k", "-bufsize", "2400k"],
)


def make(original: Path) -> str:
    light = OUT / original.parent.name / "video.mp4"
    if light.exists() and light.stat().st_mtime >= original.stat().st_mtime:
        return "kept"
    light.parent.mkdir(parents=True, exist_ok=True)
    tmp = light.with_suffix(".tmp.mp4")
    for enc in ENCODERS:
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(original), "-vf", SCALE, "-pix_fmt", "yuv420p",
               *enc, *AUDIO, "-movflags", "+faststart", str(tmp)]
        if subprocess.run(cmd, capture_output=True, timeout=600).returncode == 0:
            break
    else:
        tmp.unlink(missing_ok=True)
        return "failed"
    if tmp.stat().st_size >= original.stat().st_size:  # already light: the original is served
        tmp.unlink()
        return "skipped"
    tmp.replace(light)
    return "made"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    clips = sorted(SRC.glob("*/video.mp4"))
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(args.workers) as pool:
        for r in pool.map(make, clips):
            counts[r] = counts.get(r, 0) + 1
    print({"clips": len(clips), **counts})


if __name__ == "__main__":
    main()
