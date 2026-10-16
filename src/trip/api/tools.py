"""Public Trip adapter; schema and session restoration remain owned by Trip."""

import copy
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from agents import load_skill, permit_tool
from corpus.releases import Binding, bind, resolve_binding
from corpus.retrieval import RetrievalEngine
from corpus.snapshot import shared

from ..agent import langchain_chat
from ..domain.card import Question
from ..domain.compile import UnhandledSignal
from ..domain import drill
from ..domain.deck import Deck
from ..domain.state import TripState
from ..infrastructure.catalog import Catalog
from ..infrastructure.clef import Judge
from ..infrastructure.looks import Looks, photo_cues
from ..infrastructure.profile import USER_ID, ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import ROOT, Settings, load
from ..infrastructure.web import Web
from .engine import Engine, TurnInput


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experience: Literal["first", "returning"] | None = None
    start_with: Literal["nothing", "saved", "must", "itinerary"] | None = None
    user_id: str | None = Field(None, pattern=USER_ID.pattern)
    remember: bool = False
    profile: dict[str, str | None] | None = None


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")
    state: TripState
    card: Deck | Question | None
    transcript: list[dict]
    corpus_binding: Binding | None = None


class Tools:
    def __init__(self, engine: Engine):
        if engine.store.root is not None:
            raise ValueError("harness tools require a memory store")
        self.engine = engine
        self.skill = load_skill(Path(__file__).parent.parent / "skills.yaml")

    def _emit(self, emit):
        def bound(event, data):
            binding = getattr(self.engine, "corpus_binding", None)
            if binding is not None and event == "done" and "search_input" in data:
                data = {**data, "search_input": {**data["search_input"], "corpus_binding": binding.model_dump(mode="json")}}
            emit(event, data)
        return bound

    def create(self, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        return self.engine.create(inp.experience, inp.start_with, inp.user_id, inp.remember, inp.profile)

    def load(self, sid: str) -> dict:
        return self.engine.load(sid)

    def read(self, sid: str, operation: str, payload: dict | None = None) -> dict:
        if operation not in {"readback", "search_input"}:
            raise ValueError(f"trip does not accept {operation}")
        session = self.engine.store.get(sid)
        with session.lock:
            if operation == "readback":
                return self.engine._readback(session.state)
            try:
                si = self.engine._compile(session.state).model_dump(mode="json")
            except UnhandledSignal as exc:
                raise ValueError(str(exc)) from exc
            binding = getattr(self.engine, "corpus_binding", None)
            return {**si, "corpus_binding": binding.model_dump(mode="json")} if binding is not None else si

    def apply(self, sid: str, operation: str, payload: dict, emit) -> dict:
        if operation == "refine":
            permit_tool(self.skill, "trip.refine")
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 1000 or set(payload) != {"text"}:
                raise ValueError("text must be 1-1000 characters")
            self.engine.refine(sid, text.strip(), self._emit(emit))
            return self.load(sid)
        if operation != "turn":
            raise ValueError(f"trip does not accept {operation}")
        permit_tool(self.skill, "trip.turn")
        seen = len(self.engine.store.get(sid).transcript)
        self.engine.turn(sid, TurnInput.model_validate(payload), self._emit(emit))
        ran = [t["text"] for t in self.engine.store.get(sid).transcript[seen:] if t["role"] == "system"]
        if ran:  # the agent ran this turn; internal to the harness (stripped before the web), for usage events
            emit("trace", {"path": "fallback" if any("agent_error:" in t for t in ran) else "agent"})
        return self.load(sid)

    def places(self, query: str) -> list[dict]:
        return self.engine.places(query)

    def forget(self, user_id: str) -> bool:
        return self.engine.forget(user_id)

    def snapshot(self, sid: str) -> dict:
        s = self.engine.store.get(sid)
        with s.lock:
            return Snapshot(id=s.id, state=s.state, card=s.card, transcript=s.transcript,
                            corpus_binding=getattr(self.engine, "corpus_binding", None)).model_dump(mode="json")

    def restore(self, snapshot: dict) -> None:
        data = Snapshot.model_validate(_upgrade(snapshot))
        if data.corpus_binding != getattr(self.engine, "corpus_binding", None):
            raise ValueError("Trip corpus binding mismatch; use the pinned release")
        self.engine.store.restore(Session(data.id, data.state, data.card, data.transcript))


def _upgrade(snapshot: dict) -> dict:
    """A trip saved by an older build: what later builds dropped is removed (the state refuses unknown fields), and a
    phase that no longer exists reads as chat. 50 of 556 saved trips carried these on 2026-10-16."""
    out = copy.deepcopy(snapshot)
    state = out.get("state")
    if isinstance(state, dict):
        state.pop("other_facts", None)
        meta = state.get("meta")
        if isinstance(meta, dict):
            meta.pop("requiz", None)
            if meta.get("phase") not in (None, "chat", "quiz", "review"):
                meta["phase"] = "chat"
        for item in state.get("unmapped") or ():
            if isinstance(item, dict):
                item.pop("group", None)
    return out


def create_engine(data_root: Path, *, binding: Binding | None = None,
                  retrieval: RetrievalEngine | None = None) -> Engine:
    """Harness owns persistence; the engine keeps its normal typed state in memory."""
    load_dotenv(ROOT / ".env")
    cfg = load()
    # The active corpus release, the same one Decision and Planning read (legacy root when none is published).
    binding = binding or bind(data_root)
    if retrieval is not None and retrieval.binding != binding:
        raise ValueError("retrieval corpus binding mismatch")
    data_root = resolve_binding(data_root, binding)
    snapshot = shared(data_root / "snapshot", version=binding.snapshot_version or "")
    retrieval = retrieval if retrieval is not None else RetrievalEngine.from_snapshot(snapshot, binding.region, binding=binding)
    catalog = Catalog.from_snapshot(snapshot.region(binding.region) if binding else snapshot.region(), cfg.n_min)
    catalog.release_id = binding.release_id
    catalog.dishes("")  # builds the dish index now (~1.5 s), not on the first message that names a dish
    profiles = ProfileStore(ROOT / cfg.patterns.dir, cfg.patterns) if cfg.patterns.enabled else None
    engine = Engine(catalog, cfg, SessionStore(None), langchain_chat(cfg),
                  today=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date(), profiles=profiles,
                  judge=Judge(cfg),
                  **senses(cfg, catalog, data_root=data_root, binding=binding, retrieval=retrieval))
    engine.retrieval = retrieval
    engine.corpus_binding = binding
    if engine.looks is not None and cfg.drills and not _read_drill_scores(engine):
        # no saved scores for this corpus and config: every topic's photo card is scored now, so a turn only filters it
        threading.Thread(target=_score_drills, args=(engine,), name="drill-warm", daemon=True).start()
    return engine


def drill_key(engine: Engine) -> str:
    """What the saved photo-card scores depend on: the corpus release and index, the variants, the places."""
    b = engine.corpus_binding
    raw = json.dumps([b.release_id, b.manifest_sha256, b.index_version, engine.cfg.drills, len(engine.catalog.places)]
                     if b else [None, engine.cfg.drills, len(engine.catalog.places)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _read_drill_scores(engine: Engine) -> bool:
    path = ROOT / engine.cfg.drill_scores_path
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return saved.get("key") == drill_key(engine) and engine.looks.keep_scores(saved) > 0


def write_drill_scores(engine: Engine) -> Path:
    """Offline (`python -m trip drills`): score every topic's variants and save them for the next starts."""
    _score_drills(engine)
    path = ROOT / engine.cfg.drill_scores_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": drill_key(engine), **engine.looks.kept_scores()}, ensure_ascii=False),
                    encoding="utf-8")
    return path


def _score_drills(engine: Engine) -> None:
    engine.looks.warmed.wait(600)  # after the encoders load, never next to them (two loads at once double the memory)
    engine.looks.ready(600)
    for topic in engine.cfg.drills:
        try:
            drill.build(drill.note(TripState(), topic, 0), engine.catalog, engine.looks, engine.cfg)
        except Exception:  # warming is best effort: the turn builds the card itself
            pass


def senses(cfg: Settings, catalog: Catalog, *, data_root: Path | None = None, binding: Binding | None = None,
           retrieval: RetrievalEngine | None = None) -> dict:
    """The engine's looks (corpus.index), web and photo reader, as config/trip.yaml turns them on."""
    kwargs = {"index_version": binding.index_version, "pinned": True} if binding is not None else {}
    return {"looks": Looks(catalog, data_root=data_root, retrieval=retrieval, **kwargs) if cfg.looks else None,
            "web": Web(cfg.web_base_url, ROOT / cfg.web_cache_dir, cfg.web_timeout_s, cfg.web_ttl_days)
            if cfg.web_base_url else None,
            "see": photo_cues if cfg.looks else None}
