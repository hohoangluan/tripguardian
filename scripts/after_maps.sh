#!/bin/sh
# After scripts/rerun_observe.sh prints RERUN_DONE: the TikTok chain on what is already downloaded (asr_check ->
# place_verify -> observe -> aggregate -> serving -> evaluate, scripts/tiktok_now.sh), then AFTER_RERUN_DONE so that
# scripts/after_photos.sh can follow once the photo crawl is done. Replaces scripts/after_rerun.sh.
cd "$(dirname "$0")/.." || exit 1
LOG=logs/rerun_observe.log
until grep -q RERUN_DONE "$LOG" 2>/dev/null; do sleep 120; done
sh scripts/tiktok_now.sh
echo "$(date '+%F %T') AFTER_RERUN_DONE (after_maps.sh)" >> "$LOG"
