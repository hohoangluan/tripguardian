"""Runs gmaps phases headed (stable; a person solves Google captchas in the window, as long as it takes). A guard kills the
phase's process tree when the machine has under 0.5 GB free or no place folder was written for 10 min (hung), lowers
that phase's saved tab limit by 3 and retries. Prints GMAPS_RUNNER_DONE at the end."""
import datetime, json, os, pathlib, subprocess, sys, threading, time
import psutil

PHASES = [("crawl", "throttle.json"), ("relevant", "throttle.json"), ("extremes", "throttle.json"),
          ("photos", "photos_throttle.json"), ("keywords", "keywords_throttle.json")]  # crawl first: new list places
STALL_S = 600  # no output this long = hung (photos sat 4.5 h at 1 tab, 2026-10-06): restart the phase
LOW = 0.5 * 2**30  # Windows pages before it fails; 0.5 GB (2026-10-06, RAM-tight machine)
ROOT = pathlib.Path("data/gmaps")
SHARD = os.environ.get("GMAPS_SHARD")  # "i/n": every phase split across n runners (one Python process caps ~8 tabs)
ONLY = os.environ.get("GMAPS_PHASES")  # e.g. "extremes": run only these phases
CITY = os.environ.get("GMAPS_CITY", "dalat")  # "dalat_stay": the city's lodging list (list/dalat_stay.json)


def log(*a):
    print(*a, datetime.datetime.now(), flush=True)


def gate_until():
    """The shared block gate's cooldown end (gate.py): every tab rests then, so no folder is written; not a hang."""
    try:
        return json.loads((ROOT / "block.json").read_text(encoding="utf-8")).get("until", 0)
    except (OSError, ValueError):
        return 0


def read_limit(f, default=4):
    """A phase's saved tab limit; runners share the file, so a read during another's write falls back to default."""
    try:
        return json.loads(f.read_text(encoding="utf-8"))["limit"]
    except (OSError, ValueError, KeyError):
        return default


def write_limit(f, limit):
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")  # write aside, then replace: readers never see an empty file
    tmp.write_text(json.dumps({"limit": limit}), encoding="utf-8")
    os.replace(tmp, f)


def last_write():
    """Newest place-folder change: a file written into data/gmaps/places/<fid>/ (replace = new dir entry)."""
    return max((e.stat().st_mtime for e in os.scandir(ROOT / "places") if e.is_dir()), default=0)


def run(phase, headed, limit=None):
    cmd = [sys.executable, "-u", "-m", "corpus", "gmaps", phase, "--city", CITY]
    cmd += ["--headed"] if headed else []
    cmd += ["--limit", str(limit)] if limit else []
    if SHARD:  # one process per shard, each on its own copy of the gmaps profile
        cmd += ["--shard", SHARD, "--profile", f"gmaps_s{SHARD.split('/')[0]}"]
    env = dict(os.environ, CORPUS_FIXED_TABS="1")  # tabs = the ceiling in config/queries.yaml (2026-10-06)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env=env)
    killed, start, n = [], time.time(), 0

    def guard():
        nonlocal n
        while p.poll() is None:
            n += 1
            stalled = n % 30 == 0 and time.time() - max(start, last_write(), gate_until()) > STALL_S
            if psutil.virtual_memory().available < LOW or stalled:
                try:
                    for c in psutil.Process(p.pid).children(recursive=True):
                        c.kill()
                    p.kill()
                except psutil.Error:
                    pass
                killed.append(1)
                return
            time.sleep(2)

    threading.Thread(target=guard, daemon=True).start()
    out = []
    for line in p.stdout:
        print(line, end="", flush=True)
        out.append(line)
    p.wait()
    return p.returncode, "".join(out[-30:]), bool(killed)


HEADED = os.environ.get("GMAPS_HEADLESS") != "1"  # headless: an SSH server with no screen for a person to solve in
REACHABLE = bool(os.environ.get("CORPUS_DEBUG_PORT"))  # headless tabs a person solves through DevTools
unsolved = 0

for phase, tf in PHASES:
    if ONLY and phase not in ONLY.split(","):
        continue
    for attempt in range(200):  # a retry is a RAM kill, not a failure: progress is kept in the place folders
        log(f"== {phase} {'headed' if HEADED else 'headless'} (try {attempt + 1})")
        code, tail, killed = run(phase, headed=HEADED)
        if killed:
            f = ROOT / tf
            limit = read_limit(f)
            lim = max(min(limit, 6), limit - 3)  # floor 6 (user 2026-10-06), but a RAM kill never adds tabs
            write_limit(f, lim)
            log(f"RAM_GUARD / STALL: {phase} stopped, tabs -> {lim}")
            continue
        if "login or captcha needed" in tail:
            unsolved += 1
            if not HEADED and not REACHABLE or unsolved >= 3:  # nobody can, or nobody did: stop, don't loop
                log(f"CAPTCHA: {phase} needs a login or captcha, unsolved {unsolved}x")
                log("GMAPS_RUNNER_STOPPED")
                sys.exit(1)
            log(f"CAPTCHA: {phase} not solved in 5 min, retrying (solve it in the window)")
            continue
        unsolved = 0
        log(f"{phase} finished (exit {code})")
        break
log("GMAPS_RUNNER_DONE")
