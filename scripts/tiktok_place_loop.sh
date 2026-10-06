#!/bin/sh
# Verify every matched (video, place) pair: download a batch of clips (2 accounts), asr, asr_check, place_verify, then
# delete the verified mp4s (info + frames stay, clip_removed marks them) and repeat until place_crawl has nothing left.
# Headless by default; pass --headed when a person must solve a captcha. Run from tripguardian/.
MODE=""; [ "$1" = "--headed" ] && MODE="--headed"
BATCH=${BATCH:-200}   # videos per account per round, ~15 MB each
export PYTHONIOENCODING=utf-8
prev=-1
while true; do
  echo "== round $(date)"
  python -u -m corpus tiktok place_crawl --city dalat $MODE --shard 0/2 --limit $BATCH > logs/place_loop_s0.log 2>&1 &
  p0=$!
  python -u -m corpus tiktok place_crawl --city dalat $MODE --profile tiktok2 --shard 1/2 --limit $BATCH > logs/place_loop_s1.log 2>&1 &
  wait $p0 $!
  left=$(grep -o "place_crawl dalat: [0-9]* of" logs/place_loop_s0.log | head -1 | grep -o "[0-9]*")
  echo "todo before round (shard 0): $left"
  for s in asr asr_check place_verify; do python -u -m corpus tiktok $s --city dalat; done
  python scripts/free_tiktok_clips.py --city dalat --verified
  [ "$left" = "0" ] && break
  [ "$left" = "$prev" ] && { echo "no progress, stop"; break; }
  prev=$left
done
echo PLACE_LOOP_DONE
