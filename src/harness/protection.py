"""Bounded, process-local HTTP admission; the public edge owns volumetric DDoS protection."""

import threading
import time
from collections import deque
from functools import cache
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ProtectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    per_ip_minute: int = Field(120, ge=1)
    per_user_minute: int = Field(60, ge=1)
    max_active: int = Field(16, ge=1)
    max_connections: int = Field(64, ge=1)
    read_timeout_s: float = Field(15, gt=0)
    max_keys: int = Field(10000, ge=1)


@cache
def settings() -> ProtectionSettings:
    path = Path(__file__).resolve().parents[2] / "config" / "security.yaml"
    return ProtectionSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))["http"])


class RateGate:
    def __init__(self, max_keys: int, clock: Callable[[], float] = time.monotonic):
        self.max_keys, self.clock = max_keys, clock
        self.windows: dict[str, deque] = {}
        self.lock = threading.Lock()
        self.next_cleanup = 0.0

    def allow(self, key: str, limit: int) -> bool:
        now = self.clock()
        with self.lock:
            if now >= self.next_cleanup:
                self.windows = {k: q for k, q in self.windows.items() if q and now - q[-1] < 60}
                self.next_cleanup = now + 60
            if key not in self.windows and len(self.windows) >= self.max_keys:
                return False
            window = self.windows.setdefault(key, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True


class ProtectedHTTPServer(ThreadingHTTPServer):
    """Limit sockets before ThreadingHTTPServer can create an unbounded number of workers."""
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, handler, cfg: ProtectionSettings):
        self.slots = threading.BoundedSemaphore(cfg.max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\nRetry-After: 1\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
