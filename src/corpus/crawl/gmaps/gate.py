"""One block gate for every gmaps tab of every shard (one file, data/gmaps/block.json).

A Google captcha or throttle is per IP and account, not per tab: while one tab waits on a captcha, the other tabs of
all shards kept opening pages, so the block never cooled (2026-10-07: 12 shards x 4 tabs, new captchas faster than a
person solved them). Now the first block report stops every tab from opening a page until the cooldown ends, and each
further block (not within a minute of the last) doubles the cooldown and takes one more tab off every process. The
penalty fades by one tab per clean DECAY_S. Reads are cached, writes are atomic; a lost update between shards only
makes the gate a little looser, never stuck.
"""

import asyncio
import json
import time
from pathlib import Path

from ..common.files import data_dir, write_json
from ..common.throttle import Throttle

BASE_COOL_S = 180  # first cooldown; doubles per penalty step
MAX_COOL_S = 1200
DECAY_S = 600  # clean time that takes one penalty step off
STEP_GAP_S = 60  # reports closer than this to the last step are the same block (many tabs see it at once)
MAX_PENALTY = 10
CACHE_S = 2.0
HOLD_S = 60  # each hold keeps the rest this much past now; a waiting tab renews it every few seconds


class Gate:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "gmaps" / "block.json"
        self._cached, self._at = {}, 0.0

    def _read(self) -> dict:
        if time.monotonic() - self._at > CACHE_S:
            try:
                self._cached = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._cached = {}
            self._at = time.monotonic()
        return self._cached

    def wait_s(self) -> float:
        return max(0.0, self._read().get("until", 0) - time.time())

    def penalty(self) -> int:
        s = self._read()
        return max(0, s.get("penalty", 0) - int((time.time() - s.get("last_block", 0)) // DECAY_S))

    def report_block(self) -> None:
        now, s = time.time(), self._read()
        penalty, stepped = self.penalty(), s.get("stepped_at", 0)
        if now - stepped > STEP_GAP_S:
            penalty, stepped = min(penalty + 1, MAX_PENALTY), now
            cool = min(BASE_COOL_S * 2 ** (penalty - 1), MAX_COOL_S)
            print(f"gmaps blocked: every tab rests {cool:.0f}s, {penalty} tab(s) fewer per process", flush=True)
        else:
            cool = 0
        state = {"until": max(s.get("until", 0), now + cool), "penalty": penalty, "last_block": now,
                 "stepped_at": stepped}
        write_json(self.path, state)
        self._cached, self._at = state, time.monotonic()

    def hold(self) -> None:
        """A captcha waits for a person: keep every tab resting (and the runner's hang guard quiet) a little longer."""
        s = dict(self._read())
        s["until"] = max(s.get("until", 0), time.time() + HOLD_S)
        write_json(self.path, s)
        self._cached, self._at = s, time.monotonic()

    def solved(self) -> None:
        """A person solved a captcha: the rest ends now, and tabs waiting on their own captcha try their page again."""
        s = dict(self._read())
        s["until"], s["solved_at"] = 0, time.time()
        write_json(self.path, s)
        self._cached, self._at = s, time.monotonic()

    def solved_at(self) -> float:
        return self._read().get("solved_at", 0)


class GateThrottle(Throttle):
    """Throttle whose tab count and pauses follow the shared gate."""

    def __init__(self, *a, gate: Gate | None = None, **kw):
        super().__init__(*a, **kw)
        self.gate = gate or Gate()

    async def __aenter__(self):
        while True:
            wait = max(self.gate.wait_s(), self._until - time.monotonic())
            if wait > 0:
                await asyncio.sleep(min(wait, 5))
            elif self._active < max(1, self.limit - self.gate.penalty()):
                self._active += 1
                return self
            else:
                self._wake.clear()
                try:  # the penalty fades on its own, without a wake-up
                    await asyncio.wait_for(self._wake.wait(), 5)
                except TimeoutError:
                    pass

    def blocked(self) -> None:
        # Not reported to the gate: a page timeout or a short review list is as likely a CPU-starved shared machine
        # (load 150 on 40 cores, headless Chrome at 95% each, 2026-10-07) as Google. Only a captcha (page.py) or a
        # sign-out rests everyone.
        super().blocked()
