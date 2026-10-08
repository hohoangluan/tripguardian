#!/bin/sh
# Start / stop the local TripGuardian stack: 2 Python APIs + the Vite web dev server.
#   ./run.sh start   start everything not already running, then print the URLs
#   ./run.sh stop    stop everything this script started (and anything still holding its ports)
# Logs: logs/run/<name>.log. PIDs: logs/run/<name>.pid.
# Env overrides: PYTHON=path/to/python (default: python on PATH).
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$PWD/src"

RUN_DIR=logs/run
PYTHON=${PYTHON:-python}
mkdir -p "$RUN_DIR"

# name | port | command (run from the repo root unless it is the web app)
SERVICES="harness|8769|$PYTHON -m harness serve --port 8769
review|8765|$PYTHON -m corpus review --city dalat
web|5173|node web/node_modules/vite/bin/vite.js web --port 5173 --strictPort"

# localhost, not 127.0.0.1: Vite may listen only on ::1.
port_open() { curl -s -m 2 -o /dev/null "http://localhost:$1/"; }

# Find the PID listening on a TCP port (Windows netstat; Git Bash has it).
port_pid() {
  netstat -ano 2>/dev/null | tr -d '\r' | awk -v p=":$1" '$1 ~ /TCP/ && $2 ~ p"$" && $4 == "LISTENING" {print $5; exit}'
}

start_one() {
  name=$1; port=$2; cmd=$3
  if port_open "$port"; then
    echo "[$name] port $port already answering, skip"
    return 0
  fi
  echo "[$name] starting on :$port"
  # shellcheck disable=SC2086
  nohup $cmd > "$RUN_DIR/$name.log" 2>&1 &
  echo $! > "$RUN_DIR/$name.pid"
}

wait_one() {
  name=$1; port=$2
  i=0
  while [ $i -lt 90 ]; do
    if port_open "$port"; then
      echo "[$name] up: http://127.0.0.1:$port"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "[$name] NOT up after 90s, see $RUN_DIR/$name.log"
  return 1
}

start() {
  if [ ! -f .env ]; then
    echo "Missing .env (copy .env.example and fill in keys)."
    exit 1
  fi
  if [ ! -d web/node_modules ]; then
    echo "web/node_modules missing: run 'cd web && npm install' first."
    exit 1
  fi
  echo "$SERVICES" | while IFS='|' read -r name port cmd; do
    start_one "$name" "$port" "$cmd"
  done
  echo "$SERVICES" | while IFS='|' read -r name port cmd; do
    wait_one "$name" "$port"
  done
  echo ""
  echo "Mo web:   http://127.0.0.1:5173/app"
  echo "Admin:    http://127.0.0.1:5173/admin"
  echo "Dung:     ./run.sh stop"
}

stop_one() {
  name=$1; port=$2
  pidfile="$RUN_DIR/$name.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null && echo "[$name] stopped pid $pid"
    rm -f "$pidfile"
  fi
  # Anything still listening on the port (started outside this script, or a stale child).
  pid=$(port_pid "$port")
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    taskkill //PID "$pid" //F >/dev/null 2>&1 && echo "[$name] killed leftover pid $pid on :$port"
  fi
}

stop() {
  echo "$SERVICES" | while IFS='|' read -r name port cmd; do
    stop_one "$name" "$port"
  done
  echo "Done."
}

case "$1" in
  start) start ;;
  stop) stop ;;
  *) echo "usage: $0 {start|stop}"; exit 2 ;;
esac
