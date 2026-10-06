"""Runs gmaps phases headed (stable; a person solves Google captchas in the window, 5 min per try). A guard kills the
phase's process tree when the machine has under 0.5 GB free or no place folder was written for 10 min (hung), lowers
that phase's saved tab limit by 3 and retries. Prints GMAPS_RUNNER_DONE at the end."""
import datetime, json, os, pathlib, subprocess, sys, threading, time
import psutil

PHASES = [("extremes", "throttle.json"), ("photos", "photos_throttle.json"), ("keywords", "keywords_throttle.json")]
STALL_S = 600  # no output this long = hung (photos sat 4.5 h at 1 tab, 2026-10-06): restart the phase
LOW = 0.5 * 2**30  # Windows pages before it fails; 0.5 GB (2026-10-06, RAM-tight machine)
ROOT = pathlib.Path("data/gmaps")


def log(*a):
    print(*a, datetime.datetime.now(), flush=True)


def last_write():
    """Newest place-folder change: a file written into data/gmaps/places/<fid>/ (replace = new dir entry)."""
    return max((e.stat().st_mtime for e in os.scandir(ROOT / "places") if e.is_dir()), default=0)


def run(phase, headed, limit=None):
    cmd = [sys.executable, "-u", "-m", "corpus", "gmaps", phase, "--city", "dalat"]
    cmd += ["--headed"] if headed else []
    cmd += ["--limit", str(limit)] if limit else []
    env = dict(os.environ, CORPUS_FIXED_TABS="1")  # tabs = the ceiling in config/queries.yaml (2026-10-06)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env=env)
    killed, start, n = [], time.time(), 0

    def guard():
        nonlocal n
        while p.poll() is None:
            n += 1
            stalled = n % 30 == 0 and time.time() - max(start, last_write()) > STALL_S
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


for phase, tf in PHASES:
    for attempt in range(200):  # a retry is a RAM kill, not a failure: progress is kept in the place folders
        log(f"== {phase} headed (try {attempt + 1})")
        code, tail, killed = run(phase, headed=True)
        if killed:
            f = ROOT / tf
            limit = json.loads(f.read_text())["limit"] if f.exists() else 4
            lim = max(6, limit - 3)  # floor 6 (user 2026-10-06): tabs never drop below 6
            f.write_text(json.dumps({"limit": lim}))
            log(f"RAM_GUARD / STALL: {phase} stopped, tabs -> {lim}")
            continue
        if "login or captcha needed" in tail:
            log(f"CAPTCHA: {phase} not solved in 5 min, retrying (solve it in the window)")
            continue
        log(f"{phase} finished (exit {code})")
        break
log("GMAPS_RUNNER_DONE")
