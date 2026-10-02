#!/bin/sh
# TikTok evidence now, without waiting for the gmaps re-run (the Gemma key is shared; observe waits out HTTP 429):
# observe the clean (video, place) pairs while the local ASR transcribes the videos that have none, then
# asr_check -> place_verify -> observe the new pairs, then aggregate, serving, evaluate.
cd "$(dirname "$0")/.." || exit 1
export PYTHONIOENCODING=utf-8
LOG=logs/tiktok_now.log
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
observe() {
  for i in 1 2 3 4 5 6; do  # a lost network fails items: each run retries them
    python -u -m corpus tiktok observe --city dalat >> "$LOG" 2>&1
    tail -1 "$LOG" | grep -q '"failed"' || break
  done
}
say "observe clean pairs + asr"
observe &
python -u -m corpus tiktok asr --city dalat >> logs/tiktok_now_asr.log 2>&1
wait
for i in 1 2; do
  say "asr_check + place_verify pass $i"
  python -u -m corpus tiktok asr_check --city dalat >> "$LOG" 2>&1
  python -u -m corpus tiktok place_verify --city dalat >> "$LOG" 2>&1
done
say "observe new pairs"
observe
python -m corpus aggregate --city dalat >> "$LOG" 2>&1
python -m corpus serving --city dalat >> "$LOG" 2>&1
python -m corpus evaluate --city dalat >> "$LOG" 2>&1
say "TIKTOK_NOW_DONE"
