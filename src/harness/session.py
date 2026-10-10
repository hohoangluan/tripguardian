"""One atomic snapshot per journey, including module state and request receipts."""

import json
import re
import threading
import uuid
from pathlib import Path

from .contracts import Journey, Missing

SID = re.compile(r"[0-9a-f]{12}")


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Journey] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()
        self.feedback: list[dict] = []

    def new(self) -> Journey:
        return Journey(id=uuid.uuid4().hex[:12])

    def lock(self, jid: str):
        if not SID.fullmatch(jid):
            raise Missing(jid)
        with self._guard:
            return self._locks.setdefault(jid, threading.RLock())

    def get(self, jid: str) -> Journey:
        with self.lock(jid):
            if jid not in self._mem:
                path = self.root / f"{jid}.json" if self.root else None
                if not path or not path.exists():
                    raise Missing(jid)
                session = Journey.model_validate_json(path.read_text(encoding="utf-8"))
                if session.id != jid:
                    raise ValueError("journey file ID mismatch")
                self._mem[jid] = session
            return self._mem[jid].model_copy(deep=True)

    def append_feedback(self, record: dict) -> None:
        """Feedback lines live beside the session files (data/harness/feedback.jsonl); memory-only stores keep them."""
        with self._guard:
            if self.root:
                path = self.root.parent / "feedback.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                self.feedback.append(record)

    def list_for(self, owner: str, limit: int = 50) -> list[str]:
        """Journey IDs of one account, newest first."""
        with self._guard:
            known = dict(self._mem)
        if self.root and self.root.exists():
            files = sorted(self.root.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in files:
                if f.stem not in known and SID.fullmatch(f.stem):
                    try:
                        known[f.stem] = Journey.model_validate_json(f.read_text(encoding="utf-8"))
                    except ValueError:
                        continue
            order = {f.stem: i for i, f in enumerate(files)}
        else:
            order = {jid: -i for i, jid in enumerate(known)}
        mine = [jid for jid, j in known.items() if j.user_id == owner]
        return sorted(mine, key=lambda jid: order.get(jid, -1))[:limit]

    def save(self, session: Journey) -> None:
        with self.lock(session.id):
            if self.root:
                self.root.mkdir(parents=True, exist_ok=True)
                path = self.root / f"{session.id}.json"
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(session.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
            self._mem[session.id] = session.model_copy(deep=True)
