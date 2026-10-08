"""Bounded process quota shared by independent threads and asyncio event loops."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import threading

from pydantic import BaseModel, ConfigDict, Field
import yaml


class Limits(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    max_parallel: int = Field(default=2, ge=1, strict=True)
    max_waiting: int = Field(default=16, ge=0, strict=True)


class CapacityError(Exception):
    pass


class ProcessLimiter:
    def __init__(self, max_parallel: int, max_waiting: int):
        self.settings = Limits(max_parallel=max_parallel, max_waiting=max_waiting)
        self._lock = threading.Lock()
        self._active = 0
        self._waiting = 0

    @property
    def counts(self) -> tuple[int, int]:
        with self._lock:
            return self._active, self._waiting

    @asynccontextmanager
    async def permit(self, deadline: float):
        queued = acquired = False
        loop = asyncio.get_running_loop()
        try:
            with self._lock:
                if loop.time() >= deadline:
                    raise CapacityError('queue deadline expired')
                if self._active < self.settings.max_parallel:
                    self._active += 1
                    acquired = True
                elif self._waiting < self.settings.max_waiting:
                    self._waiting += 1
                    queued = True
                else:
                    raise CapacityError('agent queue full')
            while not acquired:
                with self._lock:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise CapacityError('queue deadline expired')
                    if self._active < self.settings.max_parallel:
                        self._waiting -= 1
                        queued = False
                        self._active += 1
                        acquired = True
                if not acquired:
                    await asyncio.sleep(min(0.005, remaining))
            yield
        finally:
            with self._lock:
                if queued:
                    self._waiting -= 1
                if acquired:
                    self._active -= 1


def load_limiter() -> ProcessLimiter:
    path = Path(__file__).resolve().parents[2] / 'config' / 'agents.yaml'
    settings = Limits.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
    return ProcessLimiter(settings.max_parallel, settings.max_waiting)
