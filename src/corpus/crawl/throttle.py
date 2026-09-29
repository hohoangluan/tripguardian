"""Self-tuning tab count (AIMD): one more tab per clean streak, half as many plus a cooldown when blocked.

The limit reached is saved, so the next run starts at the last stable level instead of probing from scratch.
"""

import asyncio
import json
import time
from pathlib import Path

from .files import write_json


class Throttle:
    def __init__(self, path: Path, start: int, hi: int, grow_after: int = 5, cooldown_s: float = 60):
        self.path, self.hi, self.grow_after, self.cooldown_s = path, max(1, hi), grow_after, cooldown_s
        try:
            start = json.loads(path.read_text(encoding="utf-8"))["limit"]
        except (OSError, ValueError, KeyError):
            pass
        self.limit = min(max(1, start), self.hi)
        self._active = self._streak = 0
        self._until = 0.0  # no new tab opens before this monotonic time
        self._wake = asyncio.Event()

    async def __aenter__(self):
        while True:
            wait = self._until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            elif self._active < self.limit:
                self._active += 1
                return self
            else:
                self._wake.clear()
                await self._wake.wait()

    async def __aexit__(self, *exc):
        self._active -= 1
        self._wake.set()

    def success(self) -> None:
        self._streak += 1
        if self._streak >= self.grow_after and self.limit < self.hi:
            self._set(self.limit + 1)

    def blocked(self) -> None:
        self._until = time.monotonic() + self.cooldown_s
        self._set(max(1, self.limit // 2))

    def _set(self, limit: int) -> None:
        if limit != self.limit:
            print(f"tabs: {self.limit} -> {limit}")
        self.limit, self._streak = limit, 0
        write_json(self.path, {"limit": limit})
        self._wake.set()
