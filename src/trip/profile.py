"""Stored voting history per user (docs/TRIP_UNDERSTANDING.md §17): data/trip/profiles/<user_id>.json.

The user id is opaque. Until login exists it is whatever the client keeps; a login later binds it to an account. Health
and body signals never reach this file (patterns.votes_from_state does not vote on them).
"""

import json
import re
import threading
from datetime import date
from pathlib import Path

from .patterns import Pattern, Summary, detect
from .settings import PatternSettings

USER_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
MAX_SESSIONS = 200  # oldest summaries beyond this are dropped


class ProfileStore:
    def __init__(self, root: Path, cfg: PatternSettings):
        self.root, self.cfg = root, cfg
        self._lock = threading.Lock()

    def _path(self, user_id: str) -> Path:
        if not USER_ID.fullmatch(user_id):
            raise ValueError("user_id must be 8-64 letters, digits, '-' or '_'")
        return self.root / f"{user_id}.json"

    def history(self, user_id: str) -> list[Summary]:
        path = self._path(user_id)
        with self._lock:
            return self._read(path)

    @staticmethod
    def _read(path: Path) -> list[Summary]:
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [Summary.model_validate(x) for x in raw["sessions"]]
        except (OSError, ValueError, KeyError):  # an unreadable file is an empty history, never a failed trip
            return []

    def patterns(self, user_id: str, today: date) -> list[Pattern]:
        return detect(self.history(user_id), self.cfg, today)

    def record(self, user_id: str, summary: Summary) -> None:
        """One summary per session id: recording the same session again replaces it."""
        path = self._path(user_id)
        with self._lock:
            kept = [s for s in self._read(path) if s.sid != summary.sid] + [summary]
            body = {"sessions": [s.model_dump(mode="json") for s in kept[-MAX_SESSIONS:]]}
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)

    def forget(self, user_id: str) -> bool:
        path = self._path(user_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True
