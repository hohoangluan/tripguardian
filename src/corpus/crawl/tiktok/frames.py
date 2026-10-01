"""Keyframes of a saved video, shared by asr_check (names on screen) and place_verify: videos/<video_id>/frames/f1..fN.jpg."""

import subprocess
from pathlib import Path

FRAMES = 4
FRAME_WIDTH = 512  # enough to read signs and overlays, small enough for four images per call


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
