"""One atomic snapshot per journey, including module state and request receipts."""

import json
import re
import threading
import uuid
from pathlib import Path

from .contracts import Journey

SID = re.compile(r"[0-9a-f]{12}")


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Journey] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def new(self) -> Journey:
        return Journey(id=uuid.uuid4().hex[:12])

    def lock(self, jid: str):
        if not SID.fullmatch(jid):
            raise KeyError(jid)
        with self._guard:
            return self._locks.setdefault(jid, threading.RLock())

    def get(self, jid: str) -> Journey:
        with self.lock(jid):
            if jid not in self._mem:
                path = self.root / f"{jid}.json" if self.root else None
                if not path or not path.exists():
                    raise KeyError(jid)
                session = Journey.model_validate_json(path.read_text(encoding="utf-8"))
                if session.id != jid:
                    raise ValueError("journey file ID mismatch")
                self._mem[jid] = session
            return self._mem[jid].model_copy(deep=True)

    def save(self, session: Journey) -> None:
        with self.lock(session.id):
            if self.root:
                self.root.mkdir(parents=True, exist_ok=True)
                path = self.root / f"{session.id}.json"
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(session.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
            self._mem[session.id] = session.model_copy(deep=True)
