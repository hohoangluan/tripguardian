#!/bin/sh
# After scripts/rerun_observe.sh prints RERUN_DONE: TikTok observe (needs the Gemma key free of the gmaps run), then
# aggregate, serving, evaluate again so the video evidence is in. Safe to run again any time (cached per place).
cd "$(dirname "$0")/.." || exit 1
export PYTHONIOENCODING=utf-8
LOG=logs/rerun_observe.log
until grep -q RERUN_DONE "$LOG" 2>/dev/null; do sleep 300; done
echo "$(date '+%F %T') tiktok observe" >> "$LOG"
for i in 1 2 3 4 5 6; do  # a lost network fails items: each run retries them
  python -u -m corpus tiktok observe --city dalat >> "$LOG" 2>&1
  tail -1 "$LOG" | grep -q '"failed"' || break
done
python -m corpus aggregate --city dalat >> "$LOG" 2>&1
python -m corpus serving --city dalat >> "$LOG" 2>&1
python -m decision evaluate >> "$LOG" 2>&1
echo "$(date '+%F %T') AFTER_RERUN_DONE" >> "$LOG"
