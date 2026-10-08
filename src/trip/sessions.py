"""Conversation sessions: in memory, mirrored to data/trip/sessions/<id>.json so a reload or restart resumes."""

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .questions import Question
from .state import TripState

SID = re.compile(r"[0-9a-f]{12}")


@dataclass
class Session:
    id: str
    state: TripState
    card: Question | None = None
    transcript: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class SessionStore:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._guard = threading.Lock()

    def new(self, state: TripState) -> Session:
        s = Session(uuid.uuid4().hex[:12], state)
        with self._guard:
            self._mem[s.id] = s
        return s

    def restore(self, s: Session) -> None:
        """Restore an in-memory snapshot owned by the harness."""
        if not SID.fullmatch(s.id):
            raise ValueError(s.id)
        with self._guard:
            self._mem[s.id] = s

    def get(self, sid: str) -> Session:
        if not SID.fullmatch(sid):
            raise KeyError(sid)
        with self._guard:
            if sid in self._mem:
                return self._mem[sid]
            path = self.root / f"{sid}.json" if self.root else None
            if not path or not path.exists():
                raise KeyError(sid)
            d = json.loads(path.read_text(encoding="utf-8"))
            s = Session(sid, TripState.model_validate(d["state"]),
                        Question.model_validate(d["card"]) if d.get("card") else None, d.get("transcript", []))
            self._mem[sid] = s
            return s

    def save(self, s: Session) -> None:
        if not self.root:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        body = {"id": s.id, "state": s.state.model_dump(mode="json"),
                "card": s.card.model_dump(mode="json") if s.card else None, "transcript": s.transcript}
        tmp = self.root / f"{s.id}.json.tmp"
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{s.id}.json")
