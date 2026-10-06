"""python -m corpus build: one incremental build from whatever the crawls have written so far (docs/CORPUS.md §CLI).

qc -> every source's observe (travellers' reports included) -> judge (dedup, status, audit) -> aggregate -> serving. Every step skips work whose
input did not change (qc and observe by input hash, the Judge by labels and decisions already written), so a build
after a crawl added reviews only reads, labels and aggregates what is new. A step that fails (network, quota) is
reported and the build goes on with the files already on disk; the next build picks it up. `every` repeats the
build every N minutes while crawls keep adding data.
"""

import asyncio
import time
import traceback

from .aggregate import run as aggregate_run
from .serving import run as serving_run
from . import judge
from .crawl.gmaps import qc as gmaps_qc
from .observe import gmaps as gmaps_observe, official as official_observe, reports as reports_observe, tiktok as tiktok_observe
from .observe.gmaps import photos as gmaps_photo_observe
from .crawl.common.files import now

STEPS = (
    ("gmaps qc", lambda city: gmaps_qc.run(city)),
    ("gmaps observe", lambda city: gmaps_observe.run(city)),
    ("gmaps photo_observe", lambda city: gmaps_photo_observe.run(city)),
    ("tiktok observe", lambda city: tiktok_observe.run(city)),
    ("official observe", lambda city: official_observe.run(city)),
    ("reports observe", lambda city: reports_observe.run(city)),
    ("judge dedup", lambda city: judge.PHASES["dedup"](city)),
    ("judge status", lambda city: judge.PHASES["status"](city)),
    ("judge audit", lambda city: judge.PHASES["audit"](city)),
    ("aggregate", lambda city: aggregate_run(city)),
    ("serving", lambda city: serving_run(city)),
)


def once(city: str, skip: set[str] = frozenset(), steps=STEPS) -> dict[str, str]:
    """Every step in order; step name -> ok | failed | skipped."""
    out = {}
    for name, fn in steps:
        if name in skip or name.split()[0] in skip:
            out[name] = "skipped"
            continue
        print(f"build {city}: {name} {now()}", flush=True)
        try:
            res = fn(city)
            if asyncio.iscoroutine(res):
                asyncio.run(res)
            out[name] = "ok"
        except (Exception, SystemExit) as e:  # SystemExit: a step found no model endpoint
            traceback.print_exc()
            print(f"build {city}: {name} failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
            out[name] = "failed"
    print(f"build {city}: done {now()} {out}", flush=True)
    return out


def run(city: str, every: float | None = None, skip: set[str] = frozenset()) -> None:
    while True:
        once(city, skip)
        if not every:
            return
        time.sleep(every * 60)
