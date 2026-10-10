#!/usr/bin/env bash
# Overnight benchmark on the UIT Gemma (docs/P2_TRIP_UNDERSTANDING.md §16): briefs, the live styles, then the offline styles on the
# same serving data for comparison. Resumable: run it again and it continues where it stopped.
#
#   setsid nohup scripts/bench_live.sh [DAY] > /dev/null 2>&1 &
#
# DAY (default today) names the output: data/bench/live-DAY/ and data/bench/offline-DAY/, log in data/bench/live-DAY/log.txt.
# USER_SIM_* default to the AGENT_* values of .env (the same Gemma on UIT).

set -u
cd "$(dirname "$0")/.."
DAY="${1:-$(date +%Y%m%d)}"
LIVE="data/bench/live-$DAY"
OFFLINE="data/bench/offline-$DAY"
mkdir -p "$LIVE"
LOG="$LIVE/log.txt"
exec >> "$LOG" 2>&1

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }   # .env has lines bash cannot source
export USER_SIM_API_KEY="${USER_SIM_API_KEY:-$(env_value USER_SIM_API_KEY)}"
export USER_SIM_BASE_URL="${USER_SIM_BASE_URL:-$(env_value USER_SIM_BASE_URL)}"
export USER_SIM_MODEL="${USER_SIM_MODEL:-$(env_value USER_SIM_MODEL)}"
[ -n "$USER_SIM_API_KEY" ] || export USER_SIM_API_KEY="$(env_value AGENT_API_KEY)"
[ -n "$USER_SIM_BASE_URL" ] || export USER_SIM_BASE_URL="$(env_value AGENT_BASE_URL)"
[ -n "$USER_SIM_MODEL" ] || export USER_SIM_MODEL="$(env_value AGENT_MODEL)"

PY=.venv/bin/python
step() { echo "== $(date '+%F %T') $*"; }

# A failed attempt (network, quota) is retried with --resume: finished rows are kept.
retry() {
  for attempt in 1 2 3 4 5; do
    "$@" && return 0
    step "attempt $attempt failed (exit $?), waiting 5 min"
    sleep 300
  done
  return 1
}

step "start: user sim $USER_SIM_MODEL at $USER_SIM_BASE_URL, pid $$"
step "briefs (one USER_SIM call per trip without one; config/bench_trips.yaml is saved after each)"
retry $PY -m bench generate --briefs --live || step "briefs incomplete: brief rows of trips without one are skipped"

step "live: chatter + brief (Trip Agent and USER_SIM on the UIT Gemma) -> $LIVE"
retry $PY -m bench run --live --styles chatter,brief --out "$LIVE" --resume || step "live run incomplete"

step "offline: tapper + baseline + brief (keyword fallback) on the same data -> $OFFLINE"
retry $PY -m bench run --styles tapper,baseline,brief --out "$OFFLINE" --resume || step "offline run incomplete"

step "done"
for d in "$LIVE" "$OFFLINE"; do
  echo "--- $d/summary.csv"
  cat "$d/summary.csv" 2>/dev/null
done
touch "$LIVE/DONE"
