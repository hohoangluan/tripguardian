#!/bin/sh
# After both scripts/after_rerun.sh (AFTER_RERUN_DONE) and the gmaps photos crawl (its "done" line in
# logs/gmaps_photos.log): read the photos (gmaps photo_observe, retried while places fail), then aggregate, serving,
# evaluate. Safe to run again (cached per place).
cd "$(dirname "$0")/.." || exit 1
export PYTHONIOENCODING=utf-8
LOG=logs/rerun_observe.log
until grep -q AFTER_RERUN_DONE "$LOG" 2>/dev/null && grep -q "done, the rest in errors" logs/gmaps_photos.log 2>/dev/null; do
  sleep 300
done
echo "$(date '+%F %T') photo observe" >> "$LOG"
for i in 1 2 3 4 5 6; do  # a lost network fails items: each run retries them
  python -u -m corpus gmaps photo_observe --city dalat >> "$LOG" 2>&1
  tail -1 "$LOG" | grep -q '"failed"' || break
done
python -m corpus aggregate --city dalat >> "$LOG" 2>&1
python -m corpus serving --city dalat >> "$LOG" 2>&1
python -m corpus evaluate --city dalat >> "$LOG" 2>&1
echo "$(date '+%F %T') AFTER_PHOTOS_DONE" >> "$LOG"
