#!/bin/sh
# Re-run gmaps observe on the current prompts / ontology, unattended (docs/plans/CORPUS_QUALITY.md V1).
# 1. wait until the UIT Gemma endpoint answers (campus network), checking every 5 min
# 2. gate: scripts/observe_prompt_eval.py must pass (no known error back, >= 80% positive cases), else stop
# 3. key the gold labels by content (review.labels.migrate) and keep a copy of the old observations
# 4. observe (again while places failed, at most 3 runs), then aggregate, serving, evaluate
# Run detached so it outlives the Claude session:
#   Start-Process -WindowStyle Hidden D:\AppDownload\Git\usr\bin\sh.exe -ArgumentList scripts/rerun_observe.sh
cd "$(dirname "$0")/.." || exit 1
export PYTHONIOENCODING=utf-8
mkdir -p logs
LOG=logs/rerun_observe.log
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
say "start, waiting for the UIT endpoint"
until curl -s -m 15 -o /dev/null -w '%{http_code}' https://llm.uit.edu.vn/gemma/v1/models | grep -q '^[24]'; do
  sleep 300
done
say "UIT reachable, prompt eval"
if ! python scripts/observe_prompt_eval.py >> "$LOG" 2>&1; then
  say "GATE FAILED: prompts not re-run, see the eval output above"
  exit 1
fi
python -c "import sys; sys.path.insert(0, 'src'); from corpus.review import labels; print('labels migrated', labels.migrate())" >> "$LOG" 2>&1
[ -d data/gmaps/observations_before_v6 ] || cp -r data/gmaps/observations data/gmaps/observations_before_v6
for i in 1 2 3; do
  say "observe run $i"
  python -u -m corpus gmaps observe --city dalat >> "$LOG" 2>&1
  tail -1 "$LOG" | grep -q '"failed"' || break
done
python -m corpus aggregate --city dalat >> "$LOG" 2>&1
python -m corpus serving --city dalat >> "$LOG" 2>&1
python -m corpus evaluate --city dalat >> "$LOG" 2>&1
say "RERUN_DONE"
