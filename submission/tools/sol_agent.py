"""Run an agent on the Judge-API model (gpt-6.1-sol / terra) with repo tools + live web search.

Usage:
  python3 -I sol_agent.py --task-file task.md --log run.log [--model cx/gpt-6.1-sol] [--max-turns 80]

Tools given to the model:
  read_file(path, offset, limit)   repo files only; secrets blocked
  list_dir(path)                   repo dirs only
  grep(pattern, path, glob)        ripgrep/grep -rn, capped output
  write_file(path, content)        only under submission/
  run(command)                     allowlisted read-only/test commands, 600 s timeout
  web_search                       built-in, live
The API key is read from the repo .env and never echoed. Final answer is printed and written to --log.
"""
import argparse
import json
import pathlib
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path("/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian").resolve()
SCRATCH = pathlib.Path(__file__).resolve().parent
WRITE_ROOT = REPO / "submission"
BLOCKED = re.compile(r"(^|/)(\.env[^/]*|certs|accounts|cookies?[^/]*|\.git|node_modules|\.venv|venv)(/|$)|secret|token|credential|\.pem$|\.key$", re.I)
ALLOWED_CMD = re.compile(
    r"^(ls|wc|find|git (ls-files|log|show --stat|diff --stat)|grep|rg|head|tail|du|"
    r"\.venv/bin/python -m pytest|python3? -m pytest|uv run pytest|"
    r"\.venv/bin/python scripts/journey_sim\.py|python3? scripts/journey_sim\.py|"
    r"\.venv/bin/python -I -c|python3 -I -c|jq)\b"
)
DENY_IN_CMD = re.compile(r"--agent|\.env|certs|accounts|cookie|urllib|requests|socket|subprocess|os\.system|rm |unlink|rmtree|>|curl|wget|open\([^)]*['\"][wa]", re.I)
MAX_OUT = 60_000

TOOLS = [
    {"type": "web_search"},
    {"type": "function", "name": "read_file", "description": "Read a text file in the repo (path relative to repo root). Returns numbered lines.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "description": "1-based start line"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"type": "function", "name": "list_dir", "description": "List a directory in the repo.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"type": "function", "name": "grep", "description": "Search regex in repo files. Returns path:line:text, capped.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}},
    {"type": "function", "name": "write_file", "description": "Write a whole file under submission/ (path relative to repo root). Overwrites.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"type": "function", "name": "run", "description": "Run an allowlisted read-only or test shell command from the repo root (ls, wc, find, grep, git ls-files/log, pytest, scripts/journey_sim.py without --agent, python3 -I -c for read-only counting). 600 s timeout.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
]


def load_env() -> dict:
    env = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def repo_path(rel: str) -> pathlib.Path:
    p = (REPO / rel).resolve()
    if REPO not in p.parents and p != REPO:
        raise ValueError("path outside repo")
    if BLOCKED.search(str(p.relative_to(REPO))):
        raise ValueError("path blocked (secrets/private)")
    return p


def tool_read_file(path, offset=1, limit=800):
    p = repo_path(path)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    offset = max(1, int(offset or 1))
    limit = min(int(limit or 800), 3000)
    chunk = lines[offset - 1: offset - 1 + limit]
    body = "\n".join(f"{i}\t{l[:2000]}" for i, l in enumerate(chunk, offset))
    return f"[{path}: lines {offset}-{offset + len(chunk) - 1} of {len(lines)}]\n{body}"


def tool_list_dir(path="."):
    p = repo_path(path)
    items = sorted(p.iterdir())
    return "\n".join(f"{'d' if x.is_dir() else 'f'} {x.relative_to(REPO)}" for x in items if not BLOCKED.search(str(x.relative_to(REPO))))[:MAX_OUT]


def tool_grep(pattern, path=".", glob=None):
    repo_path(path)
    cmd = ["grep", "-rnI", "-E", pattern, path, "--exclude-dir=.git", "--exclude-dir=node_modules", "--exclude-dir=.venv",
           "--exclude-dir=data", "--exclude=.env*", "--exclude-dir=certs"]
    if glob:
        cmd.append(f"--include={glob}")
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120).stdout
    lines = [l[:400] for l in out.splitlines() if not BLOCKED.search(l.split(":", 1)[0])]
    return "\n".join(lines[:400]) + (f"\n[... {len(lines) - 400} more]" if len(lines) > 400 else "")


def tool_write_file(path, content):
    p = (REPO / path).resolve()
    if WRITE_ROOT not in p.parents:
        raise ValueError("writes allowed only under submission/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {path} ({len(content)} chars)"


def tool_run(command):
    if not ALLOWED_CMD.match(command.strip()) or DENY_IN_CMD.search(command):
        raise ValueError("command not allowlisted")
    r = subprocess.run(command, cwd=REPO, shell=True, capture_output=True, text=True, timeout=600)
    out = (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else ""))
    return f"[exit {r.returncode}]\n" + (out[-MAX_OUT:] if len(out) > MAX_OUT else out)


IMPL = {"read_file": tool_read_file, "list_dir": tool_list_dir, "grep": tool_grep, "write_file": tool_write_file, "run": tool_run}


def call(env, model, items):
    body = {"model": model, "input": items, "tools": TOOLS}
    req = urllib.request.Request(
        env["JUDGE_BASE_URL"].rstrip("/") + "/responses", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {env['JUDGE_API_KEY']}", "Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=1200) as resp:
                return json.load(resp)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            detail = e.read()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
            print(f"  ! api error (attempt {attempt + 1}): {detail!r}", flush=True)
            time.sleep(20 * (attempt + 1))
    raise SystemExit("api failed 4 times")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--model", default="cx/gpt-6.1-sol")
    ap.add_argument("--max-turns", type=int, default=80)
    args = ap.parse_args()

    env = load_env()
    log = open(args.log, "a", encoding="utf-8")
    items = [{"role": "user", "content": pathlib.Path(args.task_file).read_text(encoding="utf-8")}]
    final = ""
    for turn in range(1, args.max_turns + 1):
        data = call(env, args.model, items)
        calls = []
        for it in data.get("output", []):
            items.append(it)
            if it.get("type") == "function_call":
                calls.append(it)
            elif it.get("type") == "web_search_call":
                q = it.get("action", {}).get("query") or it.get("action", {}).get("queries")
                log.write(f"[{turn}] web_search {q}\n")
            elif it.get("type") == "message":
                final = "\n".join(p.get("text", "") for p in it.get("content", []) if p.get("type") == "output_text")
        if not calls:
            break
        for c in calls:
            name, raw = c["name"], c.get("arguments") or "{}"
            try:
                result = IMPL[name](**json.loads(raw))
            except Exception as e:  # report tool errors back to the model
                result = f"ERROR: {e}"
            log.write(f"[{turn}] {name} {raw[:200]} -> {len(str(result))} chars\n")
            items.append({"type": "function_call_output", "call_id": c["call_id"], "output": str(result)[:MAX_OUT * 2]})
        log.flush()
    log.write("\n===== FINAL =====\n" + final + "\n")
    log.close()
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
