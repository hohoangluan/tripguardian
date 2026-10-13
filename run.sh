#!/bin/sh
# Start / stop TripGuardian.
#   ./run.sh start      dev: harness + analytics (private, :8770) + review + Vite dev server (localhost only)
#   ./run.sh stop       stop the dev stack (and anything still holding its ports)
#   ./run.sh prod       production deploy: db backup + migrate, thumbnails, build web into a staging dir (slim +
#                       precompressed) and copy it over web/dist only when it built, SearXNG, (re)start harness and the
#                       public web server on :28899, notify worker, Cloudflare tunnel, then a smoke test
#   ./run.sh prod-stop  stop the production stack (tunnel included)
#   ./run.sh prewarm    fill the coach / flight caches for the next weeks (cron, once a day; scripts/prewarm_transit.py)
#   ./run.sh db         start the project Postgres (container tripguardian-pg, 127.0.0.1:5433), create roles, migrate
#   ./run.sh db-backup  pg_dump into data/backup/pg/<date>.sql.gz, keep the newest 14
# Logs: logs/run/<name>.log. PIDs: logs/run/<name>.pid.
# Env overrides: PYTHON (default .venv python, else python on PATH), PUBLIC_PORT (28899),
#   TUNNEL_TOKEN_FILE (default ~/.cloudflared/tripguardian.token; no file = no tunnel),
#   HARNESS_GPU (default 0: the GPU the harness embeds the user's look / photo on, corpus.index).
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$PWD/src"

RUN_DIR=logs/run
if [ -z "$PYTHON" ]; then
  for p in .venv/bin/python .venv/Scripts/python.exe; do [ -x "$p" ] && PYTHON=$p && break; done
fi
PYTHON=${PYTHON:-python}
# Live crawls (flights, lodging) open a browser through corpus.crawl: with no Chrome installed, use Playwright's own.
if [ -z "$CORPUS_BROWSER_CHANNEL" ] && [ ! -x /opt/google/chrome/chrome ] && [ -d .cache/ms-playwright ]; then
  export CORPUS_BROWSER_CHANNEL=chromium PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
fi
PUBLIC_PORT=${PUBLIC_PORT:-28899}
TUNNEL_TOKEN_FILE=${TUNNEL_TOKEN_FILE:-$HOME/.cloudflared/tripguardian.token}
mkdir -p "$RUN_DIR"

# name | port | command (run from the repo root unless it is the web app)
SERVICES="harness|8769|$PYTHON -m harness serve --port 8769
analytics|8770|$PYTHON -m analytics serve --port 8770
review|8765|$PYTHON -m corpus review --city dalat
web|5173|node web/node_modules/vite/bin/vite.js web --port 5173 --strictPort"

# Production: only what the internet may reach (web/server.mjs keeps /admin and the review API private).
# The harness never inherits a dev APP_BASE_URL / TG_TEST_LOGIN from this shell (it reads the public one from .env:
# a dev value 403s every POST, test login must stay off); it gets one GPU for corpus.index (Trip looks and photos).
HARNESS_GPU=${HARNESS_GPU:-0}
PROD_SERVICES="harness|8769|env -u APP_BASE_URL -u TG_TEST_LOGIN CUDA_VISIBLE_DEVICES=$HARNESS_GPU $PYTHON -m harness serve --port 8769
public|$PUBLIC_PORT|node web/server.mjs $PUBLIC_PORT"

# Workers with no port: name | command. The notification worker plans, checks the forecast and sends web push.
WORKERS="notify|$PYTHON -u -m notify run"

worker_start() {
  echo "$WORKERS" | while IFS='|' read -r name cmd; do
    pidfile="$RUN_DIR/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "[$name] already running pid $(cat "$pidfile")"
      continue
    fi
    echo "[$name] starting"
    # shellcheck disable=SC2086
    nohup $cmd > "$RUN_DIR/$name.log" 2>&1 &
    echo $! > "$pidfile"
  done
}

worker_stop() {
  echo "$WORKERS" | while IFS='|' read -r name cmd; do
    pidfile="$RUN_DIR/$name.pid"
    [ -f "$pidfile" ] && kill "$(cat "$pidfile")" 2>/dev/null && echo "[$name] stopped pid $(cat "$pidfile")"
    rm -f "$pidfile"
  done
}

# localhost, not 127.0.0.1: Vite may listen only on ::1.
port_open() { curl -s -m 2 -o /dev/null "http://localhost:$1/"; }

# Find the PID listening on a TCP port: ss on Linux (own processes only), netstat on Windows / Git Bash.
port_pid() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnpH "sport = :$1" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -n 1
  else
    netstat -ano 2>/dev/null | tr -d '\r' | awk -v p=":$1" '$1 ~ /TCP/ && $2 ~ p"$" && $4 == "LISTENING" {print $5; exit}'
  fi
}

kill_pid() {
  if command -v taskkill >/dev/null 2>&1; then taskkill //PID "$1" //F >/dev/null 2>&1; else kill "$1" 2>/dev/null; fi
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
  worker_start
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
    kill_pid "$pid" && echo "[$name] killed leftover pid $pid on :$port"
  fi
}

stop() {
  echo "$SERVICES" | while IFS='|' read -r name port cmd; do
    stop_one "$name" "$port"
  done
  worker_stop
  echo "Done."
}

# Cloudflare tunnel from a connector token. The routes (hostname -> local port) live in the Cloudflare dashboard:
# after connecting, print them so a wrong token is noticed at once.
tunnel_start() {
  if [ ! -f "$TUNNEL_TOKEN_FILE" ]; then
    echo "[tunnel] no token file $TUNNEL_TOKEN_FILE, skip (public web only on 127.0.0.1:$PUBLIC_PORT)"
    return 0
  fi
  if ! command -v cloudflared >/dev/null 2>&1; then
    echo "[tunnel] cloudflared not installed, skip"
    return 1
  fi
  pidfile="$RUN_DIR/tunnel.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[tunnel] already running pid $(cat "$pidfile")"
    return 0
  fi
  # A connector started by hand with the same token: adopt it rather than add a second one.
  running=$(pgrep -f -- "run --token-file $TUNNEL_TOKEN_FILE" 2>/dev/null | head -n 1)
  if [ -n "$running" ]; then
    echo "$running" > "$pidfile"
    echo "[tunnel] already running pid $running (adopted)"
    return 0
  fi
  echo "[tunnel] connecting"
  nohup cloudflared tunnel --no-autoupdate run --token-file "$TUNNEL_TOKEN_FILE" > "$RUN_DIR/tunnel.log" 2>&1 &
  echo $! > "$pidfile"
  i=0
  while [ $i -lt 30 ]; do
    if grep -q "Updated to new configuration" "$RUN_DIR/tunnel.log" 2>/dev/null; then
      echo "[tunnel] up; routes from the dashboard:"
      grep "Updated to new configuration" "$RUN_DIR/tunnel.log" | tail -n 1 | grep -o '\\"hostname\\":\\"[^\\]*\\",\\"service\\":\\"[^\\]*' | sed 's/\\"//g; s/hostname://; s/,service:/  ->  /; s/^/    /'
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "[tunnel] NOT connected after 30s, see $RUN_DIR/tunnel.log"
  return 1
}

# SearXNG for the Trip agent's web_search (docker/searxng/README.md): start the container, or create it once.
SEARX_CONTAINER=tripguardian-searxng
searx_start() {
  if ! command -v docker >/dev/null 2>&1; then echo "[searxng] docker missing, the agent runs without web search"; return 0; fi
  if docker ps --format '{{.Names}}' | grep -qx "$SEARX_CONTAINER"; then
    echo "[searxng] running"
  elif docker ps -a --format '{{.Names}}' | grep -qx "$SEARX_CONTAINER"; then
    docker start "$SEARX_CONTAINER" >/dev/null && echo "[searxng] started"
  else
    mkdir -p .cache/searxng
    docker run -d --name "$SEARX_CONTAINER" --restart unless-stopped -p 127.0.0.1:8888:8080 \
      -e SEARXNG_SECRET="$(openssl rand -hex 32)" -v "$PWD/docker/searxng:/etc/searxng" \
      -v "$PWD/.cache/searxng:/var/cache/searxng" searxng/searxng:latest >/dev/null && echo "[searxng] created"
  fi
}

# Build into a staging dir and copy it over web/dist only once it built: an `npm run build` straight into dist empties
# the live site while it runs, and a failed build leaves it 404. Old hashed assets stay for tabs still open.
build_web() {
  stage=web/.deploy-build
  echo "[build] web into $stage (typecheck, vite, slim snapshot, brotli/gzip)"
  { (cd web && node_modules/.bin/tsc -b && node_modules/.bin/vite build --outDir .deploy-build --emptyOutDir) &&
    PROD_DIST="$PWD/$stage" node web/scripts/prod_assets.mjs; } > "$RUN_DIR/build.log" 2>&1 ||
    { echo "[build] FAILED, live site untouched, see $RUN_DIR/build.log"; return 1; }
  mkdir -p web/dist
  cp -a "$stage/." web/dist/ && echo "[build] copied over web/dist"
}

# After a deploy: the harness env is the production one, test login is off, a guest can sign in and open a trip.
smoke() {
  pid=$(cat "$RUN_DIR/harness.pid" 2>/dev/null)
  if [ -n "$pid" ] && tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -q '^TG_TEST_LOGIN=1'; then
    echo "[smoke] FAIL: harness runs with TG_TEST_LOGIN=1"; return 1
  fi
  base=$(env_value APP_BASE_URL)
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PUBLIC_PORT/api/auth/test/login")
  [ "$code" = "404" ] || { echo "[smoke] FAIL: /api/auth/test/login answers $code (must be 404)"; return 1; }
  # the session cookie is Secure (https): over local http it is sent by hand
  cookie=$(curl -s -D - -o /dev/null -X POST -H "Origin: $base" "http://127.0.0.1:$PUBLIC_PORT/api/auth/guest" |
    tr -d '\r' | sed -n 's/^[Ss]et-[Cc]ookie: \(tg_session=[^;]*\).*/\1/p' | head -n 1)
  [ -n "$cookie" ] || { echo "[smoke] FAIL: POST /api/auth/guest gave no tg_session cookie"; return 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Origin: $base" -H "Cookie: $cookie" -H 'Content-Type: application/json' \
    -d '{"experience":"first","start_with":"nothing"}' "http://127.0.0.1:$PUBLIC_PORT/api/harness/sessions")
  [ "$code" = "200" ] || [ "$code" = "201" ] || { echo "[smoke] FAIL: guest POST /api/harness/sessions -> $code"; return 1; }
  echo "[smoke] ok: production env, no test login, guest can open a trip"
}

prod() {
  if [ ! -f .env ]; then
    echo "Missing .env (copy .env.example and fill in keys)."
    exit 1
  fi
  if [ ! -d web/node_modules ]; then
    echo "web/node_modules missing: run 'cd web && npm install' first."
    exit 1
  fi
  if [ ! -f web/public/data/snapshot.json ]; then
    echo "web/public/data/snapshot.json missing: unpack the data zip or run web/scripts/export_snapshot.py."
    exit 1
  fi
  [ -f data/index/current ] || echo "[index] data/index/current missing: no photo cards on Hiểu chuyến đi (python -m corpus index)"
  echo "[db] backup + migrate"
  db_backup || exit 1
  $PYTHON -m db migrate > "$RUN_DIR/migrate.log" 2>&1 || { echo "[db] migrate FAILED, see $RUN_DIR/migrate.log"; exit 1; }
  echo "[build] thumbnails (new photos only)"
  $PYTHON web/scripts/make_thumbs.py > "$RUN_DIR/thumbs.log" 2>&1 || echo "[build] thumbnails failed (originals are served instead), see $RUN_DIR/thumbs.log"
  build_web || exit 1
  searx_start
  # a deploy runs the new code: whatever answers on the ports now is stopped first
  echo "$PROD_SERVICES" | while IFS='|' read -r name port cmd; do
    stop_one "$name" "$port"
  done
  echo "$PROD_SERVICES" | while IFS='|' read -r name port cmd; do
    start_one "$name" "$port" "$cmd"
  done
  echo "$PROD_SERVICES" | while IFS='|' read -r name port cmd; do
    wait_one "$name" "$port" || exit 1
  done || exit 1
  worker_stop >/dev/null
  worker_start
  tunnel_start
  smoke
  echo ""
  echo "Local:    http://127.0.0.1:$PUBLIC_PORT/  (landing) · /app"
  echo "Dung:     ./run.sh prod-stop"
}

prod_stop() {
  if [ -f "$RUN_DIR/tunnel.pid" ]; then
    kill "$(cat "$RUN_DIR/tunnel.pid")" 2>/dev/null && echo "[tunnel] stopped pid $(cat "$RUN_DIR/tunnel.pid")"
    rm -f "$RUN_DIR/tunnel.pid"
  fi
  echo "$PROD_SERVICES" | while IFS='|' read -r name port cmd; do
    stop_one "$name" "$port"
  done
  worker_stop
  echo "Done."
}

# Project Postgres: its own container on 127.0.0.1:5433 (5432 on this machine belongs to something else).
PG_CONTAINER=tripguardian-pg
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }

db() {
  if [ -z "$(env_value POSTGRES_PASSWORD)" ]; then
    echo "POSTGRES_PASSWORD missing in .env (see .env.example)."
    exit 1
  fi
  if ! docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "[db] creating container $PG_CONTAINER"
    docker run -d --name "$PG_CONTAINER" --restart unless-stopped -p 127.0.0.1:5433:5432 \
      -v tripguardian-pgdata:/var/lib/postgresql/data -e POSTGRES_PASSWORD="$(env_value POSTGRES_PASSWORD)" \
      postgres:16 >/dev/null || exit 1
  elif [ "$(docker inspect -f '{{.State.Running}}' "$PG_CONTAINER")" != "true" ]; then
    echo "[db] starting container $PG_CONTAINER"
    docker start "$PG_CONTAINER" >/dev/null || exit 1
  fi
  i=0
  until docker exec "$PG_CONTAINER" pg_isready -h 127.0.0.1 -U postgres -q 2>/dev/null; do
    i=$((i + 1))
    [ $i -ge 60 ] && { echo "[db] NOT ready after 60s"; exit 1; }
    sleep 1
  done
  $PYTHON -m db bootstrap && $PYTHON -m db migrate
}

db_backup() {
  mkdir -p data/backup/pg
  out="data/backup/pg/$(date +%Y-%m-%d_%H%M).sql.gz"
  docker exec "$PG_CONTAINER" pg_dump -U postgres tripguardian | gzip > "$out" || { echo "[db] backup FAILED"; rm -f "$out"; exit 1; }
  echo "[db] backup $out"
  ls -1t data/backup/pg/*.sql.gz | tail -n +15 | while read -r old; do rm -f "$old"; done
}

case "$1" in
  start) start ;;
  stop) stop ;;
  prod) prod ;;
  prod-stop) prod_stop ;;
  prewarm) shift; exec $PYTHON -u scripts/prewarm_transit.py "$@" ;;
  db) db ;;
  db-backup) db_backup ;;
  *) echo "usage: $0 {start|stop|prod|prod-stop|prewarm|db|db-backup}"; exit 2 ;;
esac
