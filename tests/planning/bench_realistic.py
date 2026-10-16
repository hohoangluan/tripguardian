"""p50 / p95 of building each realistic case and of the edits (spec §8), no network. --render DIR writes each case's
plan as text, so a person can read the old and the new engine side by side.

    .venv/bin/python tests/planning/bench_realistic.py --runs 3 --render logs/planning_realistic/before
"""

import argparse
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from realistic_cases import CASES, decision, engine, pick, render, run_case  # noqa: E402

TARGET_P95 = {"create": 2.0, "reorder": 0.05, "drop_place": 0.05, "move_place": 0.1, "set_day_window": 1.0,
              "set_lodging": 1.0}


def settle(eng, sid: str, limit_s: float = 120.0) -> None:
    """Wait for the session's background work (suggestions, better_order: spec §8 "Tính nền") to finish, as a person
    reads the answer before the next tap; the next edit is then timed alone, not against the last one's thread."""
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        base = eng._base.get(sid)
        if base is None or not base.pending:
            return
        time.sleep(0.01)


def p95(xs):
    return sorted(xs)[max(0, math.ceil(len(xs) * 0.95) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--render", type=Path)
    a = ap.parse_args()
    times: dict[str, list[float]] = {k: [] for k in TARGET_P95}
    who: dict[str, list] = {k: [] for k in TARGET_P95}             # (seconds, case) of each timed edit
    refused: list[str] = []
    eng = engine()
    # Live sessions run the suggestions and the better_order hint in the background (spec §8): time what the user
    # waits for, as the web server's engine does.
    eng.background = True
    for _ in range(a.runs):
        for c in CASES:
            run = run_case(c, eng)
            for sid in list(eng._base):
                settle(eng, sid)
            times["create"].append(run.seconds)
            who["create"].append((run.seconds, c["id"]))
            if a.render:
                a.render.mkdir(parents=True, exist_ok=True)
                (a.render / f"{c['id']}.txt").write_text(render(run), encoding="utf-8")
            day = next((d for d in run.days if sum(i["kind"] == "visit" for i in d["items"]) >= 2), None)
            if day is None:
                continue
            sid = eng.create(decision(c))["id"]
            view = eng.load(sid)["view"]
            view = pick(eng, sid, view)
            settle(eng, sid)
            stops = [i["place_id"] for i in view["itinerary"][day["day"] - 1]["items"] if i["kind"] == "visit"]
            start, end = view["itinerary"][day["day"] - 1]["window"]
            later = f"{min(23, int(end[:2]) + 1):02d}:{end[3:]}"           # the user stays out an hour longer
            lodge = run.home or (0.0, 0.0)
            for kind, action in (("reorder", {"type": "reorder", "day": day["day"] - 1, "order": stops[::-1]}),
                                 ("move_place", {"type": "move_place", "place": stops[0],
                                                 "day": (day["day"]) % len(view["itinerary"])}),
                                 ("drop_place", {"type": "drop_place", "place": stops[-1]}),
                                 ("set_day_window", {"type": "set_day_window", "day": day["day"] - 1, "start": start,
                                                     "end": later}),
                                 ("set_lodging", {"type": "set_lodging", "text": "Khách sạn khác",
                                                  "lat": lodge[0] + 0.003, "lng": lodge[1] + 0.003})):
                t = time.perf_counter()
                try:
                    eng.act(sid, action)
                except Exception as e:      # a refused act has no honest time: count it apart and fail the bench
                    refused.append(f"{c['id']} {kind}: {e}")
                    continue
                times[kind].append(time.perf_counter() - t)
                who[kind].append((times[kind][-1], c["id"]))
                settle(eng, sid)
    bad = 0
    for k, xs in times.items():
        if not xs:
            print(f"{k:<11} n=0    no timed samples  FAIL")
            bad += 1
            continue
        over = p95(xs) > TARGET_P95[k]
        print(f"{k:<14} n={len(xs):<4} p50={statistics.median(xs):.3f}s p95={p95(xs):.3f}s max={max(xs):.3f}s "
              f"target<{TARGET_P95[k]}s" + ("  FAIL" if over else "")
              + "  slowest: " + ", ".join(f"{cid} {sec:.2f}s" for sec, cid in sorted(who[k], reverse=True)[:3]))
        bad += over
    for line in refused:
        print(f"REFUSED {line}")
    if refused:
        print(f"{len(refused)} edits refused  FAIL")
    return 1 if bad or refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
