"""Delete the video.mp4 of TikTok videos whose evidence is finished, to free disk for the next downloads.

A video is finished when, for every place it was matched to: place_filter kept it, its transcript was checked
(asr_check), place_verify judged it, the place has been observed, and a "yes" verdict has its comments crawled.
With --verified the rule is looser: the clip goes as soon as every matched place has a place_verify verdict (the
transcript is checked and the frames are already saved), without waiting for observe or comments; comments_crawl
and place_crawl both accept clip_removed videos. Keeps video.json (with embed_url, so the clip can still be shown) and marks clip_removed, which place_crawl reads
so it does not download the clip again. Run with --dry-run first to see the count and size.
"""

import json
import sys
from pathlib import Path

from corpus.crawl.common.files import data_dir, safe_name
from corpus.crawl.tiktok.place_filter import places_by_video


def main(city: str, dry_run: bool, verified: bool = False) -> None:
    root = data_dir() / "tiktok"
    matched = places_by_video(city)
    observed = {p.stem for p in (root / "observations").glob("*.json")}
    videos = {d.name: json.loads((d / "video.json").read_text(encoding="utf-8"))
              for d in (root / "videos").iterdir() if (d / "video.json").exists()}

    def pair_done(vid: str, fid: str) -> bool:
        v = videos.get(vid)
        if not v or not v.get("transcript", {}).get("check"):
            return False
        verdicts = [p for p in v.get("places", []) if p["fid"] == fid]
        if not verdicts:
            return False
        return verdicts[0].get("verdict") != "yes" or v.get("comments_complete") is not None

    done_places = set()
    for fid in {f["fid"] for ps in matched.values() for f in ps}:
        vids = [vid for vid, ps in matched.items() if any(f["fid"] == fid for f in ps)]
        if safe_name(fid) in observed and all(pair_done(vid, fid) for vid in vids):
            done_places.add(fid)

    removable = []
    for vid, ps in matched.items():
        mp4 = root / "videos" / vid / "video.mp4"
        if vid not in videos or not mp4.exists():
            continue
        if verified:
            v = videos[vid]
            have = {p["fid"] for p in v.get("places", [])}
            ok = bool(v.get("transcript", {}).get("check")) and all(f["fid"] in have for f in ps)
        else:
            ok = all(f["fid"] in done_places for f in ps)
        if ok:
            removable.append((vid, mp4))
    size = sum(mp4.stat().st_size for _, mp4 in removable)
    print(f"done places {len(done_places)}; removable clips {len(removable)} ({size / 1e6:.0f} MB)")
    if dry_run:
        return
    for vid, mp4 in removable:
        f = root / "videos" / vid / "video.json"
        v = videos[vid]
        v["embed_url"] = f"https://www.tiktok.com/embed/v2/{vid}"
        v["clip_removed"] = True
        mp4.unlink()
        f.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"deleted {len(removable)} clips")


if __name__ == "__main__":
    city = sys.argv[sys.argv.index("--city") + 1] if "--city" in sys.argv else "dalat"
    main(city, "--dry-run" in sys.argv, "--verified" in sys.argv)
