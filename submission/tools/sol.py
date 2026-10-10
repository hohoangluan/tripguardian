"""Ask the Judge-API model (gpt-6.1-sol) a research question with live web search.

Usage:
  python3 -I sol.py --prompt-file q.md [--context a.md --context b.md] --out answer.md [--no-search]

Reads JUDGE_BASE_URL / JUDGE_API_KEY / JUDGE_MODEL from the repo .env; never prints the key.
Writes the answer + a "Nguồn web (url_citation)" list to --out, raw JSON to --out + ".json".
"""
import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path("/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian")
MODEL = "cx/gpt-6.1-sol"


def load_env() -> dict:
    env = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file")
    ap.add_argument("--prompt")
    ap.add_argument("--context", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    prompt = args.prompt or pathlib.Path(args.prompt_file).read_text(encoding="utf-8")
    for path in args.context:
        prompt += f"\n\n----- CONTEXT FILE: {path} -----\n" + pathlib.Path(path).read_text(encoding="utf-8")

    env = load_env()
    body = {"model": MODEL, "input": prompt}
    if not args.no_search:
        body["tools"] = [{"type": "web_search"}]
    req = urllib.request.Request(
        env["JUDGE_BASE_URL"].rstrip("/") + "/responses",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {env['JUDGE_API_KEY']}", "Content-Type": "application/json", "User-Agent": "curl/8.5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:500]!r}", file=sys.stderr)
        return 1

    out = pathlib.Path(args.out)
    out.with_suffix(out.suffix + ".json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    texts, cites, queries = [], {}, []
    for item in data.get("output", []):
        if item.get("type") == "web_search_call":
            queries += item.get("action", {}).get("queries") or [item.get("action", {}).get("query", "")]
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text", ""))
                for a in part.get("annotations") or []:
                    if a.get("type") == "url_citation":
                        url = a["url"].replace("?utm_source=openai", "").replace("&utm_source=openai", "")
                        cites[url] = a.get("title", "")
    md = "\n\n".join(texts)
    md += "\n\n## Nguồn web (url_citation)\n" + "\n".join(f"- {t} — {u}" for u, t in cites.items())
    md += "\n\n## Truy vấn đã chạy\n" + "\n".join(f"- {q}" for q in queries if q)
    out.write_text(md, encoding="utf-8")
    usage = data.get("usage", {})
    print(f"ok: {out} · {len(cites)} citations · {len(queries)} searches · tokens {usage.get('total_tokens')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
